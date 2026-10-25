"""budget 패키지 테스트. 여기 나오는 엑셀·CSV·알림 문구는 모두 **가상 예시**다. 실제 기관 형식이 아니다.

실행: cd notion-budget && python -m unittest discover -s tests -v
"""
import csv
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl

from budget import alerts, excel, notion, reconcile, rules
from budget.model import Kind, Transaction, assign_keys


def bank_tx(d, amt, cp="", bal=None, ref=""):
    return Transaction(date=d, amount=amt, account="하나은행", counterparty=cp, balance=bal, source="excel:hana_bank", source_ref=ref)


class AmountDate(unittest.TestCase):
    def test_amounts(self):
        for raw, want in [("12,300", 12300), ("-12,300", -12300), ("(12,300)", -12300), ("12,300원", 12300),
                          (12300, 12300), (12300.0, 12300), ("", 0), (None, 0)]:
            self.assertEqual(excel.parse_amount(raw), want, raw)
        with self.assertRaises(excel.FormatError):
            excel.parse_amount(12300.5)
        with self.assertRaises(excel.FormatError):
            excel.parse_amount("합계")

    def test_dates(self):
        self.assertEqual(excel.parse_date("2026.10.24 14:21:05"), (date(2026, 10, 24), time(14, 21, 5)))
        self.assertEqual(excel.parse_date("2026-10-24"), (date(2026, 10, 24), None))
        self.assertEqual(excel.parse_date("20261024"), (date(2026, 10, 24), None))
        self.assertEqual(excel.parse_date(datetime(2026, 10, 24, 9, 5)), (date(2026, 10, 24), time(9, 5)))


class BankExcel(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "가상_은행.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["거래내역 조회 (가상 예시)"])
        ws.append(["조회기간: 2026.10.01 ~ 2026.10.31"])
        ws.append([])
        ws.append(["거래일시", "적요", "출금(원)", "입금(원)", "거래후잔액", "메모"])
        # 최신순(은행 파일에서 흔한 정렬)
        ws.append(["2026.10.25 09:00:00", "신한카드", "312,000", "", "1,388,000", ""])
        ws.append(["2026.10.20 12:10:00", "식당", "12,000", "", "1,700,000", ""])
        ws.append(["2026.10.20 12:10:00", "식당", "12,000", "", "1,712,000", "같은 금액 두 번"])
        ws.append(["2026.10.10 08:00:00", "급여", "", "1,724,000", "1,724,000", ""])
        ws.append(["합계", "", "336,000", "1,724,000", "", ""])
        wb.save(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def test_parse_and_continuity(self):
        txs = excel.parse_file(self.path, excel.FORMATS["hana_bank"])
        self.assertEqual(len(txs), 4)                      # 합계 행 제외
        self.assertEqual(txs[0].amount, -312000)
        self.assertEqual(txs[-1].amount, 1724000)
        self.assertEqual(txs[0].source_ref, "가상_은행.xlsx:5")
        self.assertEqual(reconcile.balance_breaks(txs), [])

    def test_missing_row_breaks_balance(self):
        txs = excel.parse_file(self.path, excel.FORMATS["hana_bank"])
        del txs[1]
        breaks = reconcile.balance_breaks(txs)
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0].diff, -12000)

    def test_same_day_duplicates_are_kept(self):
        txs = excel.parse_file(self.path, excel.FORMATS["hana_bank"])
        keys = [k for k, _ in assign_keys(txs)]
        self.assertEqual(len(set(keys)), 4)
        again = [k for k, _ in assign_keys(excel.parse_file(self.path, excel.FORMATS["hana_bank"]))]
        self.assertEqual(keys, again)                      # 같은 파일 재입력은 같은 키 → 중복 입력 방지

    def test_header_not_found(self):
        fmt = excel.Format("x", "x", date=("없는열",), withdraw=("출금(원)",))
        with self.assertRaises(excel.FormatError):
            excel.parse_file(self.path, fmt)


class CardCsv(unittest.TestCase):
    def test_cp949_cancel_and_installment(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "가상_카드.csv"
            with open(p, "w", encoding="cp949", newline="") as f:
                w = csv.writer(f)
                w.writerow(["이용일자", "가맹점명", "이용금액", "할부", "상태"])
                w.writerow(["2026-10-03", "마트", "45,000", "일시불", "정상"])
                w.writerow(["2026-10-04", "가전매장", "600,000", "3개월", "정상"])
                w.writerow(["2026-10-05", "마트", "45,000", "일시불", "승인취소"])
            txs = excel.parse_file(p, excel.FORMATS["shinhan_card"])
        self.assertEqual([t.amount for t in txs], [-45000, -600000, 45000])
        self.assertEqual(txs[1].extra["installment"], "3개월")
        self.assertTrue(all(t.extra["card"] for t in txs))


class Rules(unittest.TestCase):
    def setUp(self):
        self.profile = rules.Profile(own_names=["홍길동"], own_accounts=["생활비통장"])

    def kind(self, tx):
        return rules.classify(tx, self.profile).kind

    def test_asset_moves(self):
        d = date(2026, 10, 25)
        self.assertEqual(self.kind(bank_tx(d, -312000, "신한카드", 1)), Kind.CARD_PAYMENT)
        self.assertEqual(self.kind(bank_tx(d, -500000, "홍길동", 1)), Kind.TRANSFER)
        self.assertEqual(self.kind(bank_tx(d, 500000, "홍길동", 1)), Kind.TRANSFER)
        self.assertEqual(self.kind(bank_tx(d, -300000, "자유적금", 1)), Kind.SAVINGS)
        self.assertEqual(self.kind(bank_tx(d, -400000, "대출원금상환", 1)), Kind.LOAN_REPAYMENT)
        self.assertEqual(self.kind(bank_tx(d, -12000, "식당", 1)), Kind.EXPENSE)

    def test_user_override_kept(self):
        tx = bank_tx(date(2026, 10, 25), -312000, "신한카드", 1)
        tx.kind = Kind.EXPENSE
        self.assertEqual(self.kind(tx), Kind.EXPENSE)

    def test_monthly_totals(self):
        d = date(2026, 10, 25)
        card = lambda amt: Transaction(date=d, amount=amt, account="신한카드", source="excel:shinhan_card", extra={"card": True})
        txs = [bank_tx(d, 1724000, "급여", 1), bank_tx(d, -312000, "신한카드", 1), bank_tx(d, -500000, "홍길동", 1),
               card(-45000), card(-600000), card(45000)]
        for t in txs:
            rules.classify(t, self.profile)
        self.assertEqual(rules.monthly_totals(txs)["2026-10"], {"지출": 600000, "수입": 1724000, "자산 이동": -812000})


class Installment(unittest.TestCase):
    def test_usage_vs_billed(self):
        # 가상 예시: 9월에 30만 원을 3개월 무이자로 사고, 10월 명세서에 1회차 100,000원 청구
        tx = Transaction(date=date(2026, 9, 20), amount=-300000, account="가상카드", source="excel:x", extra={"card": True},
                         billed=-100000, billing_month="2026-10", installment=(1, 3))
        cafe = Transaction(date=date(2026, 10, 2), amount=-5000, account="가상카드", source="excel:x", extra={"card": True},
                           billed=-5000, billing_month="2026-10")
        for t in (tx, cafe):
            rules.classify(t, rules.Profile())
        usage = rules.monthly_totals([tx, cafe])
        billed = rules.monthly_totals([tx, cafe], basis="billed")
        self.assertEqual((usage["2026-09"]["지출"], usage["2026-10"]["지출"]), (300000, 5000))
        self.assertNotIn("2026-09", billed)
        self.assertEqual(billed["2026-10"]["지출"], 105000)
        p = notion.transaction_properties("k#1", tx)
        self.assertEqual((p["청구 금액"]["number"], p["할부"]["rich_text"][0]["text"]["content"]), (-100000, "1/3"))


SYNTHETIC = {"demo_card": [alerts.Pattern(
    "가상 승인", "가상카드",
    re.compile(r"가상카드\((?P<card_tail>\d{4})\)\s*(?P<cancel>취소)?\s*(?P<amount>[\d,]+)원\s+(?P<month>\d{2})/(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2})\s+(?P<merchant>.+)"))]}


def alert(i, text, when=datetime(2026, 10, 25, 14, 30), sender="demo_card"):
    return alerts.Alert(f"a{i}", sender, text, when)


class Alerts(unittest.TestCase):
    def test_parse_and_refund(self):
        r = alerts.parse(alert(1, "[가상] 가상카드(1234) 12,300원 10/25 14:21 카페"), SYNTHETIC)
        self.assertTrue(r.parsed)
        self.assertEqual((r.tx.amount, r.tx.counterparty, r.tx.account, r.tx.time), (-12300, "카페", "가상카드(1234)", time(14, 21)))
        r = alerts.parse(alert(2, "[가상] 가상카드(1234) 취소 12,300원 10/25 15:00 카페"), SYNTHETIC)
        self.assertEqual(r.tx.amount, 12300)

    def test_december_alert_read_in_january(self):
        r = alerts.parse(alert(1, "가상카드(1234) 5,000원 12/31 23:50 편의점", when=datetime(2027, 1, 1, 0, 5)), SYNTHETIC)
        self.assertEqual(r.tx.date, date(2026, 12, 31))

    def test_unparsed_kept_and_format_change_warned_once(self):
        watch = alerts.FormatWatch(threshold=3)
        new_format = ["[가상] 가상카드 승인 홍*동 12,300원 일시불 10/25 카페"] * 4
        warnings = [watch.feed(alerts.parse(alert(i, t), SYNTHETIC)) for i, t in enumerate(new_format)]
        self.assertEqual(sum(w is not None for w in warnings), 1)
        self.assertIsNotNone(warnings[2])
        self.assertIsNone(watch.feed(alerts.parse(alert(9, "인증번호 [123456]"), SYNTHETIC)))  # 돈 알림 아님
        self.assertIsNone(watch.feed(alerts.parse(alert(10, "가상카드(1234) 1,000원 10/25 14:00 가게"), SYNTHETIC)))
        self.assertEqual(watch.streak["demo_card"], 0)


class ShinhanSms(unittest.TestCase):
    """신한카드 문자 형식(2026-10 실제 원문으로 확인). 이름·카드번호·금액·가맹점은 가상 값."""
    def sms(self, i, text, when):
        return alerts.parse(alerts.Alert(f"s{i}", alerts.sender_key("+82 1544-7200"), text, when))

    def test_approve_cancel_and_wrapped_merchant(self):
        r = self.sms(1, "[Web발신]\n신한법인(0000)승인 홍*동\n12,300원 10/25 14:21 가상\n상점 잔액1,987,700원", datetime(2026, 10, 25, 14, 21))
        self.assertEqual((r.tx.amount, r.tx.counterparty, r.tx.account, r.tx.extra["limit_left"]), (-12300, "가상상점", "신한카드(0000)", 1987700))
        r = self.sms(2, "[Web발신]\n신한법인(0000)취소 홍*동\n12,300원 10/25 14:30 가상\n상점", datetime(2026, 10, 25, 14, 30))
        self.assertEqual((r.tx.amount, r.tx.counterparty, r.tx.extra.get("limit_left")), (12300, "가상상점", None))

    def test_amount_on_first_line(self):
        r = self.sms(3, "[Web발신]\n신한법인(0000)승인 홍*동 5,000원\n10/25 15:00 가상_APP\n잔액1,982,700원", datetime(2026, 10, 25, 15, 0))
        self.assertEqual((r.tx.amount, r.tx.counterparty), (-5000, "가상_APP"))

    def test_limit_gap_finds_missing_alert(self):
        texts = [("10/01 09:00", "1,000", "1,999,000"), ("10/02 09:00", "2,000", "1,997,000"),
                 ("10/04 09:00", "3,000", "1,990,000")]   # 10/03에 4,000원 알림이 빠짐
        txs = [self.sms(i, f"신한법인(0000)승인 홍*동 {a}원 {d} 가상상점 잔액{l}원", datetime(2026, 10, int(d[3:5]), 9, 0)).tx
               for i, (d, a, l) in enumerate(texts)]
        gaps = reconcile.limit_gaps(txs)
        self.assertEqual([(g.after_ref, g.missing) for g in gaps], [("s1", 4000)])

    def test_limit_increase_is_not_a_gap(self):
        txs = [self.sms(i, f"신한법인(0000)승인 홍*동 {a}원 10/0{i + 1} 09:00 가상상점 잔액{l}원", datetime(2026, 10, i + 1, 9, 0)).tx
               for i, (a, l) in enumerate([("1,000", "1,000,000"), ("2,000", "1,998,000")])]  # 사이에 카드값 결제
        self.assertEqual(reconcile.limit_gaps(txs), [])

    def test_unknown_sender_kept_as_digits(self):
        self.assertEqual(alerts.sender_key("+82 1588-0000"), "15880000")


class Coverage(unittest.TestCase):
    def test_alert_coverage(self):
        d = date(2026, 10, 25)
        ex = [Transaction(date=d, amount=-12300, account="가상카드"), Transaction(date=d, amount=-5000, account="가상카드")]
        al = [Transaction(date=date(2026, 10, 26), amount=-12300, account="가상카드(1234)"),
              Transaction(date=d, amount=-9900, account="가상카드(1234)")]
        c = reconcile.alert_coverage(ex, al)
        self.assertEqual((c.matched, len(c.missed_by_alerts), len(c.alerts_without_row)), (1, 1, 1))
        self.assertEqual(c.rate, 0.5)

    def test_card_statement_diff(self):
        txs = [Transaction(date=date(2026, 10, d), amount=a, account="가상카드") for d, a in [(3, -45000), (5, 45000), (9, -20000)]]
        self.assertEqual(reconcile.card_statement_diff(txs, 20000, date(2026, 10, 1), date(2026, 10, 31)), 0)
        self.assertEqual(reconcile.card_statement_diff(txs, 22500, date(2026, 10, 1), date(2026, 10, 31)), 2500)


class Notion(unittest.TestCase):
    def test_transaction_properties(self):
        tx = Transaction(date=date(2026, 10, 25), time=time(9, 0), amount=-312000, account="하나은행", counterparty="신한카드",
                         memo="x" * 4500, kind=Kind.CARD_PAYMENT, kind_reason="은행 출금 상대가 카드사(신한카드)",
                         source="excel:hana_bank", source_ref="f.xlsx:5")
        p = notion.transaction_properties("k#1", tx)
        self.assertEqual(p["금액"], {"number": -312000})
        self.assertEqual(p["구분"]["select"]["name"], "카드대금")
        self.assertEqual(p["날짜"]["date"]["start"], "2026-10-25T09:00:00+09:00")
        self.assertEqual([len(x["text"]["content"]) for x in p["메모"]["rich_text"]], [2000, 2000, 500])
        self.assertEqual(set(p), set(notion.DATABASES["거래"]))

    def test_schema(self):
        s = notion.schema_payload("거래")
        self.assertIn({"name": "카드대금"}, s["구분"]["select"]["options"])
        self.assertEqual(s["금액"], {"number": {"format": "won"}})
        self.assertEqual(s["이름"], {"title": {}})


if __name__ == "__main__":
    unittest.main()
