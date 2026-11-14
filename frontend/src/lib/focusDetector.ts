// 집중 도우미: 웹캠 한 장면을 보고 "화면을 보고 있는지"를 판단 (MediaPipe Face Landmarker)
// - 모든 계산은 이 브라우저 안에서만 합니다. 영상·사진은 저장하거나 서버로 보내지 않아요.
// - 처음 켤 때 MediaPipe 실행 파일(wasm)과 얼굴 모델(약 3.6MB)을 인터넷에서 한 번 받아요.
import { FaceLandmarker, FilesetResolver, type FaceLandmarkerResult } from '@mediapipe/tasks-vision';

const WASM_BASE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm';
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

let shared: Promise<FaceLandmarker> | null = null;

/** 얼굴 모델을 한 번만 불러서 같이 씀 (GPU가 안 되면 CPU로) */
export function loadFaceLandmarker(): Promise<FaceLandmarker> {
  if (!shared) {
    shared = (async () => {
      const files = await FilesetResolver.forVisionTasks(WASM_BASE);
      const options = (delegate: 'GPU' | 'CPU') => ({
        baseOptions: { modelAssetPath: MODEL_URL, delegate },
        runningMode: 'VIDEO' as const,
        numFaces: 1,
        outputFaceBlendshapes: true,
      });
      try {
        return await FaceLandmarker.createFromOptions(files, options('GPU'));
      } catch {
        return FaceLandmarker.createFromOptions(files, options('CPU'));
      }
    })();
    shared.catch(() => (shared = null)); // 실패하면 다음에 다시 시도
  }
  return shared;
}

/** 한 장면 분석 결과 */
export interface FaceFrame {
  face: boolean; // 얼굴이 보임
  away: boolean; // 고개를 돌렸거나 눈동자가 옆으로 많이 감 (화면 밖을 봄)
  closed: boolean; // 눈을 감음
  /** 눈동자 위치 (눈 너비에 대한 비율, 양쪽 평균). 멍하니 있는지 볼 때 씀 */
  iris?: [number, number];
}

// 얼굴 점 번호 (MediaPipe Face Mesh 478점)
const NOSE = 1;
const FACE_LEFT = 234;
const FACE_RIGHT = 454;
const FOREHEAD = 10;
const CHIN = 152;
const L_IRIS = 468;
const R_IRIS = 473;
const L_EYE = [33, 133] as const; // 눈꼬리, 눈 안쪽
const R_EYE = [362, 263] as const;
const L_LID = [159, 145] as const; // 위·아래 눈꺼풀
const R_LID = [386, 374] as const;

// 판단 기준 (태블릿을 내려다보며 읽는 자세는 "딴 데 봄"이 되지 않도록 넉넉하게)
const YAW_LIMIT = 0.17; // 코가 얼굴 가운데에서 이만큼 벗어나면 고개를 돌린 것
const PITCH_MIN = 0.32; // 코 높이 비율이 이보다 작으면 위를 봄
const PITCH_MAX = 0.8; // 이보다 크면 아래를 많이 봄
const GAZE_SIDE = 0.62; // 눈동자가 옆으로 이만큼 가면 화면 밖을 봄
const BLINK = 0.55; // 양쪽 눈 감음 점수 평균

export function analyzeFace(result: FaceLandmarkerResult): FaceFrame {
  const lm = result.faceLandmarks?.[0];
  if (!lm || lm.length < 478) return { face: false, away: false, closed: false };

  const score = (name: string) => result.faceBlendshapes?.[0]?.categories.find((c) => c.categoryName === name)?.score ?? 0;

  // 고개 좌우: 코가 얼굴 양 끝 사이 어디쯤 있는지 (가운데 0.5)
  const yaw = (lm[NOSE].x - lm[FACE_LEFT].x) / (lm[FACE_RIGHT].x - lm[FACE_LEFT].x || 1e-6);
  // 고개 위아래: 코가 이마~턱 사이 어디쯤 있는지
  const pitch = (lm[NOSE].y - lm[FOREHEAD].y) / (lm[CHIN].y - lm[FOREHEAD].y || 1e-6);
  const headAway = Math.abs(yaw - 0.5) > YAW_LIMIT || pitch < PITCH_MIN || pitch > PITCH_MAX;

  // 눈동자 옆으로 (아래 보기는 글 읽기라서 빼고, 옆·위만)
  const gazeSide = Math.max(score('eyeLookOutLeft'), score('eyeLookInLeft'), score('eyeLookOutRight'), score('eyeLookInRight'));
  const gazeUp = Math.max(score('eyeLookUpLeft'), score('eyeLookUpRight'));
  const eyesAway = gazeSide > GAZE_SIDE || gazeUp > GAZE_SIDE;

  const closed = (score('eyeBlinkLeft') + score('eyeBlinkRight')) / 2 > BLINK;

  // 눈동자 위치: 눈 너비 기준 가로, 눈꺼풀 사이 기준 세로 (양쪽 평균)
  const rel = (iris: number, [a, b]: readonly [number, number], [top, bottom]: readonly [number, number]): [number, number] => {
    const w = Math.hypot(lm[b].x - lm[a].x, lm[b].y - lm[a].y) || 1e-6;
    const h = Math.abs(lm[bottom].y - lm[top].y) || 1e-6;
    return [(lm[iris].x - lm[a].x) / w, (lm[iris].y - lm[top].y) / Math.max(h, w * 0.2)];
  };
  const l = rel(L_IRIS, L_EYE, L_LID);
  const r = rel(R_IRIS, R_EYE, R_LID);

  return {
    face: true,
    away: headAway || eyesAway,
    closed,
    iris: [(l[0] + r[0]) / 2, (l[1] + r[1]) / 2],
  };
}
