"""사용법: python verify_fixtures.py /path/to/Box/weekly-report"""
import copy, hashlib, json, shutil, sys, tempfile
from pathlib import Path

KIT=Path(__file__).resolve().parent
SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(SOURCE))
from weekly_report.weekly import run_weekly,select_dailies,_semantic_issues
from weekly_report.pptgen import apply_updates,collapse_milestones,layout_milestones,generate_ppt
from weekly_report.core import validate_schema

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for part in ['data/master','data/raw'] for p in (root/part).rglob('*.json')}
results=[]
def check(name,ok,detail=''):
    results.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=detail))
# results는 매 실행 생성물이므로 지우고 다시 만든다
shutil.rmtree(KIT/'results',ignore_errors=True)
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'root'; shutil.copytree(KIT/'fixture-root',root)
    template=SOURCE/'주간업무PPT_Template_v2.pptx'
    before=hashes(root)
    for case in read(KIT/'manifest.json'):
        pid=case['project_id']; out=KIT/'results'/pid
        p=read(root/f'data/master/projects/{pid}.json')
        validate_schema(p,root/'schemas/project.schema.json')
        selected=select_dailies(root,pid,'2026-W39')
        check(pid+' Daily 필터',[d['daily_id'] for d in selected]==case['expected_selected_daily_ids'])
        wp,cp,rp=run_weekly(root,pid,'2026-W39',out)
        w,c=read(wp),read(cp)
        check(pid+' 스키마 및 mock 실행',w['source_daily_ids']==case['expected_selected_daily_ids'] and c['pinned_facts']!=[])
        check(pid+' 검증 보고서 과제별 분리',rp==out/f'output/{pid}/validation_2026-W39.txt')
        if pid=='P-ROL-102':
            updated,warnings,changed=apply_updates(p,w)
            check('일정 변경 overlay와 baseline 보존',updated['milestones'][4]['plan']=='2026-09-30' and updated['milestones'][4]['baseline']=='2026-09-25' and p['milestones'][4]['plan']=='2026-09-25')
            check('완료 하위행 접기',len(collapse_milestones(updated['milestones']))==9)
            rows=copy.deepcopy(updated['milestones'])
            for row in rows: row['status']='진행'
            first,rest=layout_milestones(rows)
            check('접기 불가능한 12행의 초과 대응',len(first)<=9 and len(first)+len(rest)==12,'9행 + (계속) 장 3행 이월')
        try:
            generate_ppt(root,root/f'data/master/projects/{pid}.json',wp,cp,root/'templates/missing.pptx',out/'output/test.pptx')
            check(pid+' 템플릿 누락 감지',False)
        except FileNotFoundError as e:
            check(pid+' 템플릿 누락 감지','main_table' in str(e))
        if template.exists():
            notes=generate_ppt(root,root/f'data/master/projects/{pid}.json',wp,cp,template,out/f'output/{pid}_2026-W39.pptx')
            problems=[n for n in notes if n.startswith('PPT 검사 문제')]
            check(pid+' PPT 생성·재검사(색·글꼴·표·장수)',not problems,'; '.join(problems)[:200])
        else:
            check(pid+' PPT 생성·재검사(색·글꼴·표·장수)',False,'v2 템플릿 없음 → BLOCKED')
    pid='P-APC-101'; out=KIT/'results'/pid
    path=out/f'data/derived/weekly/{pid}/2026-W39.json'
    old=read(path)
    run_weekly(root,pid,'2026-W39',out)
    check('재실행 revision 증가',read(path)['meta']['revision']==old['meta']['revision']+1)
    wp,cp,rp=run_weekly(root,pid,'2026-W37',KIT/'results/no-daily')
    check('메모 없는 주 AI 호출 생략',read(wp)['no_change'] and not read(wp)['source_daily_ids'])
    # 이전 누적의 고정 사실을 생성 결과가 누락할 때 보존하는지 확인
    prev=root/f'data/derived/cumulative/{pid}/2026-W38.json'
    v=read(prev); v['pinned_facts']=[dict(text='이전 고정 사실 유지',source_ids=[pid],kind='fact',changed=False)]
    prev.write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8')
    wp,cp,rp=run_weekly(root,pid,'2026-W39',KIT/'results/pinned-regression')
    check('이전 pinned_facts 누락 방지',any(x['text']=='이전 고정 사실 유지' for x in read(cp)['pinned_facts']))
    p=read(root/f'data/master/projects/{pid}.json')
    bad=dict(headline=dict(text='입력에 없는 4% 개선',source_ids=[pid]),progress=[],next_plan=[],issues=[],milestone_updates=[])
    check('입력에 없는 4 수치 검출',any('수치' in x for x in _semantic_issues(bad,{pid},p,'입력 수치 없음')))
    bad['headline']=dict(text='근거 검사',source_ids=['D-260922-unknown-01'])
    check('미존재 source ID 검출',any('근거' in x for x in _semantic_issues(bad,{pid},p,'')))
    check('원본 master/raw 보존',before==hashes(root))
write=KIT/'validation_results.json'
write.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=['# 예시 JSON 검증 결과','',f'소스: {SOURCE}', '검증 환경: Python '+sys.version.split()[0], '', '모든 업무 내용은 합성 데이터. mock 실행은 AI 요약 품질이나 사내 API 연결을 검증하지 않음.','', '| 검사 | 결과 | 비고 |','|---|---|---|']
report.extend('| '+r['check']+' | '+r['status']+' | '+r['detail']+' |' for r in results)
report+=['','## 남은 제한','- mock 응답은 고정값이라 AI 요약 품질·사내 API 연결은 검증하지 않음.','- OPS 실적형은 저장 스키마와 생성 경로가 준비되지 않아 이번 5종에서 제외.','- 완성 예시 PPT(templates/주간업무_예시_조립자동보정팀_W39.pptx)가 없어 시각 기준 비교는 하지 않음.']
(KIT/'validation_report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
print(json.dumps(dict(total=len(results),passed=sum(r['status']=='PASS' for r in results),failed=[r['check'] for r in results if r['status']=='FAIL']),ensure_ascii=False))
