// 내 정보: 프로필 사진, 이름·이메일, 비밀번호 변경
import { Camera, KeyRound, Save, Trash2 } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';
import { api } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Avatar } from '../../components/Avatar';
import { features } from '../../config';

/** 가운데를 정사각형으로 잘라 256px JPEG로 줄임 (업로드 용량·개인정보 메타데이터 줄이기) */
async function toSquareJpeg(file: File, size = 256): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  canvas
    .getContext('2d')!
    .drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, size, size);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('이미지를 바꾸지 못했어요'))), 'image/jpeg', 0.88),
  );
}

/** 실서버 모드: 백엔드에 내 정보 수정 API가 아직 없어서 보기만 */
function ProfileReadOnly() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <section className="card stack">
      <div className="profile-head">
        <Avatar user={user} size={96} />
        <div className="stack-sm">
          <h3>{user.name}</h3>
          <span className="muted">
            {user.role === 'teacher' ? '선생님' : '학생'} · @{user.username}
          </span>
        </div>
      </div>
      <p className="muted small">이름·사진·비밀번호 바꾸기는 준비 중이에요.</p>
    </section>
  );
}

export function ProfileTab() {
  return features.profileEdit ? <ProfileEditor /> : <ProfileReadOnly />;
}

function ProfileEditor() {
  const { user, updateUser } = useAuth();
  const [name, setName] = useState(user?.name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  const [photoBusy, setPhotoBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  if (!user) return null;

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg('');
    try {
      updateUser(await api.updateMe({ name: name.trim(), email: email.trim() || undefined }));
      setMsg('저장했어요');
    } catch (err) {
      setMsg((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function onPhoto(file: File) {
    if (!file.type.startsWith('image/')) return setMsg('이미지 파일만 올릴 수 있어요');
    setPhotoBusy(true);
    setMsg('');
    try {
      const { avatarUrl } = await api.uploadAvatar(await toSquareJpeg(file));
      updateUser(await api.updateMe({ avatarUrl }));
    } catch (err) {
      setMsg((err as Error).message);
    } finally {
      setPhotoBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function removePhoto() {
    setPhotoBusy(true);
    try {
      updateUser(await api.updateMe({ avatarUrl: null }));
    } finally {
      setPhotoBusy(false);
    }
  }

  return (
    <div className="stack">
      <form className="card stack" onSubmit={onSave}>
        <div className="profile-head">
          <div className="avatar-edit">
            <Avatar user={user} size={96} />
            <button
              type="button"
              className="btn btn-primary btn-icon avatar-cam"
              aria-label="프로필 사진 바꾸기"
              disabled={photoBusy}
              onClick={() => fileRef.current?.click()}
            >
              <Camera size={18} />
            </button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => e.target.files?.[0] && onPhoto(e.target.files[0])} />
          </div>
          <div className="stack-sm">
            <h3>프로필 사진</h3>
            <p className="muted small">원하는 사진으로 설정해 보세요. 정사각형으로 잘려서 저장돼요.</p>
            <div className="row">
              <button type="button" className="btn btn-soft btn-sm" disabled={photoBusy} onClick={() => fileRef.current?.click()}>
                <Camera size={15} /> {photoBusy ? '올리는 중…' : '사진 바꾸기'}
              </button>
              {user.avatarUrl && (
                <button type="button" className="btn btn-ghost btn-sm" disabled={photoBusy} onClick={removePhoto}>
                  <Trash2 size={15} /> 삭제
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="divider-line" />

        <div className="two-col">
          <label className="field">
            <span>이름</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="field">
            <span>이메일 (선택)</span>
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="알림을 받을 이메일" />
          </label>
          <label className="field">
            <span>아이디</span>
            <input className="input" value={user.username} disabled />
          </label>
          <label className="field">
            <span>소속</span>
            <input className="input" value={user.school ?? ''} placeholder="슈퍼스쿨을 연결하면 자동으로 채워져요" disabled />
          </label>
        </div>

        <div className="row">
          <button className="btn btn-primary" disabled={saving}>
            <Save size={16} /> {saving ? '저장 중…' : '저장'}
          </button>
          {msg && <span className="muted small">{msg}</span>}
        </div>
      </form>

      <PasswordCard />
    </div>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (next.length < 8) return setMsg({ ok: false, text: '새 비밀번호는 8자 이상이어야 해요' });
    if (next !== confirm) return setMsg({ ok: false, text: '새 비밀번호가 서로 달라요' });
    setBusy(true);
    setMsg(null);
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      setMsg({ ok: true, text: '비밀번호를 바꿨어요' });
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={onSubmit}>
      <div className="card-title" style={{ marginBottom: 0 }}>
        <KeyRound size={20} />
        <h3>비밀번호 바꾸기</h3>
      </div>
      <div className="two-col">
        <label className="field">
          <span>지금 비밀번호</span>
          <input className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </label>
        <div />
        <label className="field">
          <span>새 비밀번호</span>
          <input className="input" type="password" autoComplete="new-password" placeholder="8자 이상" value={next} onChange={(e) => setNext(e.target.value)} required />
        </label>
        <label className="field">
          <span>새 비밀번호 확인</span>
          <input className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </label>
      </div>
      <div className="row">
        <button className="btn" disabled={busy}>
          {busy ? '바꾸는 중…' : '비밀번호 바꾸기'}
        </button>
        {msg && <span className={msg.ok ? 'small' : 'error-text'}>{msg.text}</span>}
      </div>
    </form>
  );
}
