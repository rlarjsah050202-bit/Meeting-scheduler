# 링크 공유형 모임 날짜 조율 프로그램

이 프로젝트는 **이름을 입력하고, 5/7부터 6월 말까지(기본값) 저녁 6시 회식 참석 가능 여부를 날짜별로 선택**하는 간단한 웹앱입니다.

## 기능
- 링크 공유형 날짜 조율 페이지 생성
- 이름 입력 후 날짜별로 **가능 / 부분참여 / 안됨** 선택
- 부분참여는 **0.5명**으로 최종 결과에 반영
- 같은 이름으로 다시 제출하면 기존 응답 수정
- 요약 화면에서 **가장 많은 사람이 가능한 날짜** 자동 표시

## 실행 방법
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

브라우저에서 아래 주소를 여세요.
```text
http://127.0.0.1:5000
```


## 바로 링크로 쓰는 가장 쉬운 방법 (Render)
Render는 Flask 앱을 배포하면 `onrender.com` 공개 URL을 제공합니다. Render의 Flask 배포 문서도 `pip install -r requirements.txt` 빌드와 `gunicorn app:app` 시작 명령을 사용합니다.

1. GitHub에 이 폴더를 업로드
2. Render 대시보드에서 **New > Web Service** 선택
3. 저장소 연결 후 배포
4. 배포가 끝나면 공개 링크가 생성됨

이 프로젝트에는 `render.yaml`이 포함되어 있어 기본 설정값이 들어 있습니다.
