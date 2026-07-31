import { AppShell } from './components/layout/AppShell'
import { ConversationProvider } from './state/conversationStore'
import { StructuresProvider } from './state/structuresStore'
import { ThemeProvider } from './state/themeStore'

function App() {
  return (
    <ThemeProvider>
      <ConversationProvider>
        <StructuresProvider>
          <AppShell />
        </StructuresProvider>
      </ConversationProvider>
    </ThemeProvider>
  )
}

export default App
