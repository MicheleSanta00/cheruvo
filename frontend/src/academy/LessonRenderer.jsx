/**
 * LessonRenderer.jsx — monta il motore giusto in base al tipo di lezione.
 * Usato sia dal player (Academy) sia dall'anteprima live (Workspace).
 */
import QuizEngine from './QuizEngine.jsx'
import SimulatorEngine from './SimulatorEngine.jsx'
import FlashcardEngine from './FlashcardEngine.jsx'
import ScenarioEngine from './ScenarioEngine.jsx'

export default function LessonRenderer({ type, ...props }) {
  if (type === 'quiz') return <QuizEngine {...props} />
  if (type === 'simulator') return <SimulatorEngine {...props} />
  if (type === 'flashcard') return <FlashcardEngine {...props} />
  if (type === 'scenario') return <ScenarioEngine {...props} />
  return <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>
}
