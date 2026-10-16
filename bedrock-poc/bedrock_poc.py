# bedrock_poc.py — AWS Bedrock 서울 리전(ap-northeast-2) Claude 호출 PoC
#
# 목적: 폐쇄망 도입 검토 자료용으로 (1) 서울 리전으로 실제 호출이 되는지,
#       (2) 처리가 리전을 벗어나지 않는지, (3) 응답 시간과 토큰·비용이 얼마인지를 눈으로 확인.
#
# 설치:  python -m pip install boto3
# 자격증명: aws configure  또는  환경변수 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
#
# 사용:
#   python bedrock_poc.py list                    사용 가능한 Claude 모델 / 추론 프로필 조회
#   python bedrock_poc.py check                   자격증명 · 리전 · 엔드포인트 확인 (모델 호출 안 함)
#   python bedrock_poc.py ask -m <모델ID> "질문"   1회 호출
#   python bedrock_poc.py bench -m <모델ID> -n 5  N회 반복, 평균 지연·토큰·비용
import sys, json, time, argparse, datetime as dt, statistics as st

REGION = 'ap-northeast-2'          # 서울
TITLE = {'ap-northeast-2': '서울', 'ap-northeast-1': '도쿄', 'us-east-1': '버지니아', 'us-west-2': '오리건'}

# 1M 토큰당 USD. AWS Bedrock 요금 페이지에서 쓰는 모델 기준으로 채우고 쓰면 비용까지 계산됨.
# (요금은 모델·리전마다 다르고 바뀌므로 하드코딩하지 않음. --price-in / --price-out 로 줘도 됨)
PRICE = {}                         # 예: {'claude-sonnet': (3.0, 15.0)}
USD_KRW = 1400                     # --krw 로 변경


def die(msg, tip=''):
    print(f'\n[중단] {msg}', file=sys.stderr)
    if tip: print(f'       → {tip}', file=sys.stderr)
    sys.exit(1)


def boto():
    try:
        import boto3, botocore
        return boto3, botocore
    except ImportError:
        die('boto3 가 설치되어 있지 않습니다.', 'python -m pip install boto3')


def clients(region):
    boto3, botocore = boto()
    cfg = botocore.config.Config(region_name=region, retries={'max_attempts': 2, 'mode': 'standard'},
                                 read_timeout=300, connect_timeout=10)
    return boto3.client('bedrock', config=cfg), boto3.client('bedrock-runtime', config=cfg), boto3.client('sts', config=cfg)


def explain(e):
    """boto3 예외를 사람이 읽을 수 있는 원인 + 조치로"""
    name = type(e).__name__
    code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
    msg = str(e)
    if name in ('NoCredentialsError', 'PartialCredentialsError'):
        return '자격증명이 없습니다.', 'aws configure 로 등록하거나 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY 를 설정하세요.'
    if code == 'UnrecognizedClientException' or 'security token' in msg:
        return '액세스 키가 유효하지 않습니다.', 'IAM 에서 키를 다시 발급받으세요.'
    if code == 'AccessDeniedException':
        return 'IAM 권한이 없거나 모델 액세스가 승인되지 않았습니다.', \
               'Bedrock 콘솔 > Model access 에서 해당 모델을 활성화하고, IAM 에 bedrock:InvokeModel 권한을 주세요.'
    if code == 'ResourceNotFoundException':
        return '그 리전에 없는 모델 ID 입니다.', 'python bedrock_poc.py list 로 정확한 ID 를 확인하세요.'
    if code == 'ValidationException' and 'on-demand' in msg:
        return '이 모델은 모델 ID 직접 호출(온디맨드)을 지원하지 않습니다.', \
               '추론 프로필 ID 로 호출해야 합니다. list 명령의 [추론 프로필] 목록에서 고르세요. ' \
               '단, apac. 로 시작하는 교차 리전 프로필은 처리가 서울 밖으로 나갈 수 있으니 검토 자료에 쓸 때 주의.'
    if code == 'ThrottlingException':
        return '요청이 제한되었습니다.', '잠시 후 다시 시도하거나 -n 을 줄이세요.'
    if code == 'ModelNotReadyException':
        return '모델이 아직 준비되지 않았습니다.', '잠시 후 다시 시도하세요.'
    if 'EndpointConnectionError' in name or 'ConnectTimeout' in name:
        return 'Bedrock 엔드포인트에 연결하지 못했습니다.', \
               '사내 프록시를 쓰는 환경이면 HTTPS_PROXY 를 설정하고, 방화벽에서 bedrock-runtime.%s.amazonaws.com 을 허용하세요.' % REGION
    return f'{code or name}: {msg}', ''


def guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except SystemExit:
        raise
    except Exception as e:
        die(*explain(e))


# ---------- check ----------
def cmd_check(args):
    bedrock, runtime, sts = clients(args.region)
    me = guard(sts.get_caller_identity)
    print('■ 자격증명')
    print(f'   계정      {me["Account"]}')
    print(f'   주체      {me["Arn"]}')
    print('\n■ 리전 · 엔드포인트')
    print(f'   리전      {args.region} ({TITLE.get(args.region, "?")})')
    print(f'   엔드포인트 {runtime.meta.endpoint_url}')
    inside = f'.{args.region}.' in runtime.meta.endpoint_url
    print(f'   판정      {"리전 전용 엔드포인트 — 호출이 이 리전으로 들어갑니다." if inside else "리전 엔드포인트가 아닙니다. 확인 필요."}')
    models = guard(bedrock.list_foundation_models, byProvider='anthropic').get('modelSummaries', [])
    on_demand = [m for m in models if 'ON_DEMAND' in m.get('inferenceTypesSupported', [])]
    print('\n■ 모델')
    print(f'   Anthropic 모델 {len(models)}개 노출, 이 중 모델 ID 직접 호출(온디맨드) 가능 {len(on_demand)}개')
    print(f'\n다음: python bedrock_poc.py list   (정확한 모델 ID 확인)')


# ---------- list ----------
def cmd_list(args):
    bedrock, runtime, _ = clients(args.region)
    models = guard(bedrock.list_foundation_models, byProvider='anthropic').get('modelSummaries', [])
    print(f'■ {args.region} ({TITLE.get(args.region, "?")}) 의 Anthropic 모델\n')
    print(f'   {"모델 ID":<52} {"호출 방식":<22} 스트리밍')
    print('   ' + '-' * 86)
    for m in sorted(models, key=lambda x: x['modelId']):
        t = m.get('inferenceTypesSupported', [])
        how = '모델 ID 직접' if 'ON_DEMAND' in t else ('추론 프로필 필요' if 'INFERENCE_PROFILE' in t else ','.join(t))
        print(f'   {m["modelId"]:<52} {how:<22} {"O" if m.get("responseStreamingSupported") else "-"}')
    if not models:
        print('   (없음 — 리전을 확인하거나 Bedrock 콘솔 > Model access 에서 모델을 활성화하세요)')

    try:
        profs = bedrock.list_inference_profiles(typeEquals='SYSTEM_DEFINED').get('inferenceProfileSummaries', [])
    except Exception:
        profs = []
    if profs:
        print(f'\n■ 추론 프로필')
        print('   (prefix 없는 것 = 이 리전에서 처리 / apac·us 등으로 시작 = 교차 리전, 처리가 리전 밖으로 나갈 수 있음)\n')
        for p in sorted(profs, key=lambda x: x['inferenceProfileId']):
            if 'claude' not in p['inferenceProfileId'].lower(): continue
            cross = p['inferenceProfileId'].split('.')[0] in ('apac', 'us', 'eu', 'global')
            print(f'   {p["inferenceProfileId"]:<52} {"교차 리전" if cross else "리전 내"}')
    print(f'\n다음: python bedrock_poc.py ask -m <모델ID> "안녕하세요"')


# ---------- 호출 ----------
def call(runtime, model, prompt, system, max_tokens, stream, quiet=False):
    """Converse API 1회 호출 → (본문, usage, 경과ms)"""
    req = dict(modelId=model,
               messages=[{'role': 'user', 'content': [{'text': prompt}]}],
               inferenceConfig={'maxTokens': max_tokens, 'temperature': 0.2})
    if system: req['system'] = [{'text': system}]
    t0 = time.time()
    if not stream:
        r = guard(runtime.converse, **req)
        ms = (time.time() - t0) * 1000
        text = ''.join(b.get('text', '') for b in r['output']['message']['content'])
        if not quiet: print(text)
        return text, r['usage'], r.get('metrics', {}).get('latencyMs', ms)
    r = guard(runtime.converse_stream, **req)
    text, usage, first = '', {}, None
    for ev in r['stream']:
        if 'contentBlockDelta' in ev:
            d = ev['contentBlockDelta']['delta'].get('text', '')
            if d and first is None: first = (time.time() - t0) * 1000
            text += d
            if not quiet: print(d, end='', flush=True)
        elif 'metadata' in ev:
            usage = ev['metadata'].get('usage', {})
    if not quiet: print()
    ms = (time.time() - t0) * 1000
    if first is not None and not quiet: print(f'\n(첫 글자까지 {first:.0f} ms)')
    return text, usage, ms


def price_of(model, args):
    if args.price_in is not None and args.price_out is not None:
        return args.price_in, args.price_out
    for k, v in PRICE.items():
        if k in model: return v
    return None


def cost_line(model, args, tin, tout):
    p = price_of(model, args)
    if not p:
        return '   비용       요금 미설정 — --price-in / --price-out 에 1M 토큰당 USD 를 넣으면 계산됩니다'
    usd = tin / 1e6 * p[0] + tout / 1e6 * p[1]
    return f'   비용       ${usd:.5f}  (약 {usd * args.krw:,.1f}원)   [입력 ${p[0]}/1M · 출력 ${p[1]}/1M 기준]'


def cmd_ask(args):
    _, runtime, _ = clients(args.region)
    prompt = args.prompt or '안녕하세요. 지금 어떤 리전에서 응답하고 있는지는 알 수 없겠지만, 한국어로 한 문장만 답해 주세요.'
    print(f'■ 모델 {args.model}')
    print(f'■ 리전 {args.region} ({TITLE.get(args.region, "?")}) · {runtime.meta.endpoint_url}\n')
    print('─' * 70)
    text, usage, ms = call(runtime, args.model, prompt, args.system, args.max_tokens, args.stream)
    print('─' * 70)
    tin, tout = usage.get('inputTokens', 0), usage.get('outputTokens', 0)
    print(f'   응답 시간  {ms:,.0f} ms')
    print(f'   토큰       입력 {tin:,} · 출력 {tout:,} · 합계 {usage.get("totalTokens", tin + tout):,}')
    print(cost_line(args.model, args, tin, tout))
    if args.save: save(args, [{'ms': ms, 'in': tin, 'out': tout, 'text': text}])


def cmd_bench(args):
    _, runtime, _ = clients(args.region)
    prompt = args.prompt or '전자정부 프레임워크 기반 Spring MVC 프로젝트에서 테이블 하나를 변경할 때 영향도 점검 항목을 5개만 짧게 나열해 주세요.'
    print(f'■ 모델 {args.model} · {args.region} ({TITLE.get(args.region, "?")}) · {args.n}회 반복\n')
    runs = []
    for i in range(1, args.n + 1):
        text, usage, ms = call(runtime, args.model, prompt, args.system, args.max_tokens, False, quiet=True)
        tin, tout = usage.get('inputTokens', 0), usage.get('outputTokens', 0)
        runs.append({'ms': ms, 'in': tin, 'out': tout, 'text': text})
        print(f'   {i}/{args.n}   {ms:>7,.0f} ms   입력 {tin:>6,} · 출력 {tout:>6,}')
    lat = sorted(r['ms'] for r in runs)
    tin = sum(r['in'] for r in runs); tout = sum(r['out'] for r in runs)
    print(f'\n■ 결과 ({args.n}회)')
    print(f'   응답 시간  평균 {st.mean(lat):,.0f} ms · 중앙값 {st.median(lat):,.0f} ms · 최소 {lat[0]:,.0f} · 최대 {lat[-1]:,.0f}')
    print(f'   토큰       입력 합계 {tin:,} · 출력 합계 {tout:,} (1회 평균 입력 {tin / args.n:,.0f} · 출력 {tout / args.n:,.0f})')
    print(cost_line(args.model, args, tin, tout))
    print(f'   * 위 비용은 {args.n}회 합계입니다. 1회당 비용 × 예상 월 호출 건수로 월 비용을 산정하세요.')
    if args.save: save(args, runs)


def save(args, runs):
    rep = {'at': dt.datetime.now().isoformat(timespec='seconds'), 'region': args.region, 'model': args.model,
           'runs': [{k: v for k, v in r.items() if k != 'text'} for r in runs],
           'sample_output': runs[0]['text'][:2000] if runs else ''}
    with open(args.save, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(f'\n   보고서 저장 → {args.save}')


def main():
    ap = argparse.ArgumentParser(description='AWS Bedrock 서울 리전 Claude 호출 PoC')
    ap.add_argument('--region', default=REGION, help=f'기본 {REGION} (서울)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, model_required):
        p.add_argument('-m', '--model', required=model_required, help='모델 ID 또는 추론 프로필 ID (list 명령으로 확인)')
        p.add_argument('prompt', nargs='?', help='질문. 생략하면 기본 질문 사용')
        p.add_argument('-s', '--system', default='', help='시스템 프롬프트')
        p.add_argument('--max-tokens', type=int, default=1024)
        p.add_argument('--price-in', type=float, help='입력 1M 토큰당 USD')
        p.add_argument('--price-out', type=float, help='출력 1M 토큰당 USD')
        p.add_argument('--krw', type=float, default=USD_KRW, help=f'환율, 기본 {USD_KRW}')
        p.add_argument('--save', help='결과를 JSON 으로 저장할 파일명')

    sub.add_parser('check', help='자격증명 · 리전 · 엔드포인트 확인')
    sub.add_parser('list', help='사용 가능한 모델 / 추론 프로필 조회')
    a = sub.add_parser('ask', help='1회 호출'); common(a, True); a.add_argument('--stream', action='store_true', help='스트리밍 출력')
    b = sub.add_parser('bench', help='N회 반복해서 평균 지연 · 토큰 · 비용'); common(b, True); b.add_argument('-n', type=int, default=5)

    args = ap.parse_args()
    try:
        {'check': cmd_check, 'list': cmd_list, 'ask': cmd_ask, 'bench': cmd_bench}[args.cmd](args)
    except KeyboardInterrupt:
        print('\n중단했습니다.')


if __name__ == '__main__':
    for s in (sys.stdout, sys.stderr):                                # cp949 콘솔에서 한글이 안 깨지게
        try: s.reconfigure(encoding='utf-8', errors='replace')
        except Exception: pass
    main()
