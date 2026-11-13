import { ChevronRight, FileText, GraduationCap, Layers, MessageCircleQuestion, Presentation, Sparkles } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';
import { homeFor, useAuth } from '../auth/AuthContext';

const features = [
  { icon: FileText, title: '쉬운 문장으로 재구성', desc: '수업 자료를 페이지마다 짧고 쉬운 문장으로 바꾸고, 어려운 말에는 뜻을 붙여요.' },
  { icon: Layers, title: '페이지별 쉬운 설명', desc: '선생님 설명이 그 페이지에 쌓여요. 놓쳐도 돌아가면 그대로 있어요.' },
  { icon: MessageCircleQuestion, title: '수업 범위 챗봇', desc: '수업이 끝나면 확인 문제를 풀고, 배운 내용 안에서 궁금한 걸 물어봐요.' },
];

export function Home() {
  const { user, ready } = useAuth();
  if (ready && user) return <Navigate to={homeFor(user.role)} replace />;

  return (
    <>
      <section className="landing">
        <div className="landing-copy">
          <span className="chip chip-blue">
            <Sparkles size={14} /> 모두를 위한 수업 도우미
          </span>
          <h1>
            수업을
            <br />
            <em>내 속도로</em> 따라가요
          </h1>
          <p>선생님의 설명을 AI가 쉬운 문장으로 바꿔 페이지마다 쌓아 드려요. 반 친구들과 같은 자료를, 내 속도로 봐요.</p>
        </div>

        <div className="role-tiles">
          <Link to="/login" state={{ role: 'student' }} className="role-tile primary">
            <div className="role-icon">
              <GraduationCap size={30} />
            </div>
            <div>
              <strong>학생으로 시작하기</strong>
              <span>과목 코드로 참여하고 쉬운 설명 보기</span>
            </div>
            <ChevronRight className="role-arrow" />
          </Link>
          <Link to="/login" state={{ role: 'teacher' }} className="role-tile">
            <div className="role-icon">
              <Presentation size={28} />
            </div>
            <div>
              <strong>선생님으로 시작하기</strong>
              <span>과목을 열고 수업 자료 준비하기</span>
            </div>
            <ChevronRight className="role-arrow" />
          </Link>
        </div>
      </section>

      <section className="features">
        {features.map(({ icon: Icon, title, desc }) => (
          <div key={title} className="card feature">
            <div className="feature-icon">
              <Icon size={22} />
            </div>
            <h3>{title}</h3>
            <p>{desc}</p>
          </div>
        ))}
      </section>
    </>
  );
}
