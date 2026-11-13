import type { User } from '../api/types';

export function Avatar({ user, size = 32 }: { user: Pick<User, 'name' | 'avatarUrl'>; size?: number }) {
  const style = { width: size, height: size, fontSize: size * 0.42 };
  return user.avatarUrl ? (
    <img className="avatar avatar-img" src={user.avatarUrl} alt="" style={style} />
  ) : (
    <span className="avatar" aria-hidden style={style}>
      {user.name.slice(0, 1)}
    </span>
  );
}
