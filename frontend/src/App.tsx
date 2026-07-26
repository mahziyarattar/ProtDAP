import { AppShell } from './components/layout/AppShell'
import { ConversationProvider } from './state/conversationStore'

function App() {
  return (
    <ConversationProvider>
      <AppShell />
    </ConversationProvider>
  )
}

export default App
