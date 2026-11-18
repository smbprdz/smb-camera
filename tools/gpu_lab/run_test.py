"""Bounded runner for the fixed ABBA holdout. No model/phone/OBS runtime."""
from pathlib import Path
import json,subprocess,sys,time,statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ucs.process_job import ProcessJob
scripts=Path(__file__).resolve().parent
folder=Path('output/gpu-lab').resolve();folder.mkdir(parents=True,exist_ok=True)
report={'scope':'fixed generated ABBA holdout, sender-stage comparison only',
        'passed':False,'phase_timeout_seconds':60,'rows':[],'personal_media_recorded':False,
        'native_cpp_executed':False,'obs_or_live_runtime_modified':False}
try:
    for phase in range(8):
        with (folder/f'test-phase-{phase}.log').open('wb') as log:
            process=subprocess.Popen([sys.executable,str(scripts/'benchmark.py'),'--phase',str(phase)],stdout=log,stderr=subprocess.STDOUT)
            job=ProcessJob(process)
            try:code=process.wait(60)
            except subprocess.TimeoutExpired:
                job.terminate();process.wait(5);raise RuntimeError('Holdout phase exceeded 60 seconds')
            finally:job.close()
        if code:raise RuntimeError('Holdout phase failed: '+str(phase))
        result=json.loads((folder/f'test-phase-{phase}.json').read_text())
        if not result['passed']:raise RuntimeError('Holdout pixel check failed')
        report['rows'].extend(result['rows'])
        print(json.dumps({'phase':phase,'status':'pass','rows_collected':len(report['rows'])}),flush=True)
    comparisons=[]
    for size in ((1920,1080),(3840,2160)):
        ram=[r for r in report['rows'] if r['canvas']==list(size) and r['route']=='ram']
        gpu=[r for r in report['rows'] if r['canvas']==list(size) and r['route']=='gpu']
        rp=statistics.median(r['sender_wall_p95_ms'] for r in ram);gp=statistics.median(r['sender_wall_p95_ms'] for r in gpu)
        rc=statistics.median(r['sender_thread_cpu_p95_ms'] for r in ram);gc=statistics.median(r['sender_thread_cpu_p95_ms'] for r in gpu)
        # Windows thread CPU time can quantize to zero in a short phase. Never
        # turn that into a division error or a claim of zero CPU consumption.
        comparisons.append({'canvas':list(size),'sender_wall_p95_reduction':1-gp/rp,
            'sender_cpu_p95_reduction':1-gc/rc if rc>0 else None,
            'sender_wall_not_worse':gp<=rp,'gate':gp<=rp and (gp<=rp*.7 or (rc>0 and gc<=rc*.7))})
    report.update(comparisons=comparisons,passed=all(row['gate'] for row in comparisons))
except Exception as error:report['error']=str(error)
(folder/'test-result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
raise SystemExit(0 if report['passed'] else 1)
