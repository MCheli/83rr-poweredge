<template>
  <div class="terminal-container">
    <div class="terminal-header">
      Mark Cheli Developer Terminal v1.0.0 - Interactive Interface
      <br>
      Type 'help' for available commands | Type 'neofetch' for system info
    </div>

    <div class="terminal-content">
      <!-- Welcome message -->
      <div class="terminal-output">
        <span class="success-text">Welcome to Mark Cheli's Developer Terminal!</span>
        <br>
        Last login: {{ formatDate(new Date()) }} from local-machine
        <br><br>
        <span class="info-text">Tip: Try 'neofetch' to see system information or 'help' for available commands.</span>
        <br><br>
      </div>

      <!-- Command history -->
      <div
        v-for="(entry, index) in terminalHistory"
        :key="index"
        class="terminal-output"
      >
        <div class="command-line">
          <span class="terminal-prompt">mark@homelab:~$ </span>
          <span class="command-text">{{ entry.command }}</span>
        </div>
        <div v-if="entry.output === 'CLEAR_SCREEN'" class="clear-marker"></div>
        <div v-else-if="entry.output" class="command-output">
          <pre>{{ entry.output }}</pre>
        </div>
      </div>

      <!-- Current input line -->
      <div class="terminal-input-line">
        <span class="terminal-prompt">mark@homelab:~$ </span>
        <input
          ref="inputElement"
          v-model="currentInput"
          class="terminal-input"
          type="text"
          @keydown="handleKeydown"
          @focus="inputFocused = true"
          @blur="inputFocused = false"
          placeholder=""
          autocomplete="off"
          spellcheck="false"
        />
        <span v-if="inputFocused" class="terminal-cursor">_</span>
      </div>
    </div>
  </div>
</template>

<script setup>
const { executeCommand, addToHistory, navigateHistory } = useTerminal()

const terminalHistory = ref([])
const currentInput = ref('')
const inputElement = ref(null)
const inputFocused = ref(true)

// Auto-focus input when component mounts
onMounted(() => {
  nextTick(() => {
    inputElement.value?.focus()
  })

  // Keep input focused when clicking anywhere on terminal
  document.addEventListener('click', () => {
    inputElement.value?.focus()
  })
})

const formatDate = (date) => {
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const handleKeydown = async (event) => {
  if (event.key === 'Enter') {
    const command = currentInput.value.trim()

    if (command) {
      // Add command to history
      addToHistory(command)

      // Execute command
      const output = await executeCommand(command)

      // Handle special commands
      if (output === 'CLEAR_SCREEN') {
        terminalHistory.value = []
      } else {
        terminalHistory.value.push({
          command,
          output,
          timestamp: new Date()
        })
      }
    } else {
      // Empty command, just show prompt
      terminalHistory.value.push({
        command: '',
        output: '',
        timestamp: new Date()
      })
    }

    // Clear input and scroll to bottom
    currentInput.value = ''

    await nextTick()
    window.scrollTo(0, document.body.scrollHeight)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    navigateHistory('up')
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    navigateHistory('down')
  } else if (event.key === 'Tab') {
    event.preventDefault()
    // Basic tab completion could be added here
  } else if (event.ctrlKey && event.key === 'l') {
    // Ctrl+L to clear screen
    event.preventDefault()
    terminalHistory.value = []
  } else if (event.ctrlKey && event.key === 'c') {
    // Ctrl+C to cancel current input
    event.preventDefault()
    currentInput.value = ''
  }
}

// Watch for changes in currentCommand from composable (for history navigation)
const { currentCommand } = useTerminal()
watch(currentCommand, (newValue) => {
  currentInput.value = newValue
})
</script>

<style scoped>
.clear-marker {
  display: none;
}

.command-line {
  margin-bottom: 5px;
}

.command-text {
  color: #ffffff;
}

.command-output {
  margin-left: 20px;
  margin-bottom: 10px;
  color: #dddddd;
}

.command-output pre {
  font-family: inherit;
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.terminal-input-line {
  display: flex;
  align-items: center;
  margin-top: 10px;
}

.terminal-input {
  flex: 1;
  margin-left: 0;
}
</style>