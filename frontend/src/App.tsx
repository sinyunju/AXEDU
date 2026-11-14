import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { RequireRole } from './auth/RequireRole';
import { Layout } from './components/Layout';
import { SuperschoolCallback } from './pages/auth/SuperschoolCallback';
import { SuperschoolMock } from './pages/auth/SuperschoolMock';
import { Home } from './pages/Home';
import { Settings } from './pages/settings/Settings';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { Chat } from './pages/student/Chat';
import { Quiz } from './pages/student/Quiz';
import { StudentClass } from './pages/student/StudentClass';
import { StudentCourse } from './pages/student/StudentCourse';
import { StudentHome } from './pages/student/StudentHome';
import { CourseDetail } from './pages/teacher/CourseDetail';
import { LessonReview } from './pages/teacher/LessonReview';
import { LiveClass } from './pages/teacher/LiveClass';
import { TeacherDashboard } from './pages/teacher/TeacherDashboard';

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Home /> },
      { path: '/login', element: <Login /> },
      { path: '/signup', element: <Signup /> },
      { path: '/auth/superschool/callback', element: <SuperschoolCallback /> },
      { path: '/auth/superschool/mock', element: <SuperschoolMock /> },
      // 교사·학생 공용
      {
        element: <RequireRole />,
        children: [{ path: '/settings', element: <Settings /> }],
      },
      // 교사: 과목 개설 → 수업(차시) 추가 → 수업 전 자료 업로드·승인 → 수업 진행
      {
        element: <RequireRole role="teacher" />,
        children: [
          { path: '/teacher', element: <TeacherDashboard /> },
          { path: '/teacher/courses/:courseId', element: <CourseDetail /> },
          { path: '/teacher/lessons/:lessonId/review', element: <LessonReview /> },
          { path: '/teacher/lessons/:lessonId/live', element: <LiveClass /> },
        ],
      },
      // 학생: 과목 코드로 참여 → 승인된 수업 입장
      {
        element: <RequireRole role="student" />,
        children: [
          { path: '/student', element: <StudentHome /> },
          { path: '/student/courses/:courseId', element: <StudentCourse /> },
          { path: '/class/:lessonId', element: <StudentClass /> },
          { path: '/class/:lessonId/quiz', element: <Quiz /> },
          { path: '/class/:lessonId/chat', element: <Chat /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
