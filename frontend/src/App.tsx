import { AppShell } from './components/layout/AppShell'
import { ConversationProvider } from './state/conversationStore'
import { StructuresProvider } from './state/structuresStore'

function App() {
  return (
    <ConversationProvider>
      <StructuresProvider>
        <AppShell />
      </StructuresProvider>
    </ConversationProvider>
  )
}

export default App
