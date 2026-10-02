"""사용법: python verify_fixtures.py /path/to/Box/weekly-report"""
import copy, hashlib, json, shutil, sys, tempfile
from pathlib import Path

KIT=Path(__file__).resolve().parent
SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(SOURCE))
from weekly_report.weekly import run_weekly,select_dailies,_semantic_issues
from weekly_report.pptgen import apply_updates,collapse_milestones,generate_ppt
from weekly_report.core import validate_schema

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for part in ['data/master','data/raw'] for p in (root/part).rglob('*.json')}
results=[]
def check(name,ok,detail=''):
    results.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=detail))
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'root'; shutil.copytree(KIT/'fixture-root',root)
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
        # 프로젝트별 output 분리: 현재 리포트 파일명이 주차만 사용함.
        if pid=='P-ROL-102':
            updated,warnings,changed=apply_updates(p,w)
            check('일정 변경 overlay와 baseline 보존',updated['milestones'][4]['plan']=='2026-09-30' and updated['milestones'][4]['baseline']=='2026-09-25' and p['milestones'][4]['plan']=='2026-09-25')
            check('완료 하위행 접기',len(collapse_milestones(updated['milestones']))==9)
            rows=copy.deepcopy(updated['milestones'])
            for row in rows: row['status']='진행'
            check('접기 불가능한 12행의 초과 대응',len(collapse_milestones(rows))<=9,'현재 12행 그대로 반환. PPT 생성기는 표 행 수만큼 잘라서 사용함.')
        try:
            generate_ppt(root,root/f'data/master/projects/{pid}.json',wp,cp,root/'templates/주간업무PPT_Template_v2.pptx',out/'output/test.pptx')
        except FileNotFoundError:
            check(pid+' 템플릿 누락 감지',True,'실제 PPT 생성 및 시각 검증은 BLOCKED')
    pid='P-APC-101'; out=KIT/'results'/pid
    path=out/f'data/derived/weekly/{pid}/2026-W39.json'
    old=read(path)
    run_weekly(root,pid,'2026-W39',out)
    check('재실행 revision 증가',read(path)['meta']['revision']==old['meta']['revision']+1,'현재 재실행해도 revision=1')
    wp,cp,rp=run_weekly(root,pid,'2026-W37',KIT/'results/no-daily')
    check('메모 없는 주 AI 호출 생략',read(wp)['no_change'] and not read(wp)['source_daily_ids'])
    # 이전 누적의 고정 사실을 생성 결과가 누락할 때 보존하는지 확인
    prev=root/f'data/derived/cumulative/{pid}/2026-W38.json'
    v=read(prev); v['pinned_facts']=[dict(text='이전 고정 사실 유지',source_ids=[pid],kind='fact',changed=False)]
    prev.write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8')
    wp,cp,rp=run_weekly(root,pid,'2026-W39',KIT/'results/pinned-regression')
    check('이전 pinned_facts 누락 방지',any(x['text']=='이전 고정 사실 유지' for x in read(cp)['pinned_facts']),'mock이 이전 고정 사실을 반환하지 않으면 코드에서도 보존하지 않음')
    p=read(root/f'data/master/projects/{pid}.json')
    bad=dict(headline=dict(text='입력에 없는 4% 개선',source_ids=[pid]),progress=[],next_plan=[],issues=[],milestone_updates=[])
    check('입력에 없는 4 수치 검출',any('수치' in x for x in _semantic_issues(bad,{pid},p,'입력 수치 없음')),'현재 숫자 4와 39는 예외 처리되어 누락됨')
    bad['headline']=dict(text='근거 검사',source_ids=['D-260922-unknown-01'])
    check('미존재 source ID 검출',any('근거' in x for x in _semantic_issues(bad,{pid},p,'')))
    check('원본 master/raw 보존',before==hashes(root))
write=KIT/'validation_results.json'
write.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=['# 예시 JSON 검증 결과','',f'소스: {SOURCE}', '검증 환경: Python '+sys.version.split()[0], '', '모든 업무 내용은 합성 데이터. mock 실행은 AI 요약 품질이나 사내 API 연결을 검증하지 않음.','', '| 검사 | 결과 | 비고 |','|---|---|---|']
report.extend('| '+r['check']+' | '+r['status']+' | '+r['detail']+' |' for r in results)
report+=['','## 코드 검토로 확인한 추가 미구현 사항','- 지난주 weekly 입력이 항상 없음으로 전달됨.','- fit_to_budget 호출과 계속 슬라이드 생성이 구현되지 않음.','- 한글 LG Smart Regular의 ea 글꼴 설정이 구현되지 않음.','- cumulative 출력의 수치·근거에 대한 의미 검증 없음.','- 여러 과제를 같은 out-root로 실행하면 validation_{week}.txt가 덮어써짐.','- OPS 실적형은 저장 스키마와 생성 경로가 준비되지 않아 이번 5종에서 제외.','', '실제 PPT 검증은 공식 템플릿 추가 후 진행해야 함.']
(KIT/'validation_report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
print(json.dumps(dict(total=len(results),passed=sum(r['status']=='PASS' for r in results),failed=[r['check'] for r in results if r['status']=='FAIL']),ensure_ascii=False))
