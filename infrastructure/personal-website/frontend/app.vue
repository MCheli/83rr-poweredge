<template>
  <div class="terminal-container">

    <div class="terminal-content">
      <!-- Welcome message -->
      <div class="terminal-output">
        <span class="success-text">Welcome to Mark Cheli's Developer Terminal!</span>
        <br>
        Last login: {{ formatDate(new Date()) }} from local-machine
        <br><br>
        <span class="info-text">Type 'help' for available commands. Try 'linkedin' to connect.</span>
        <br><br>
      </div>

      <!-- Command history -->
      <div
        v-for="(entry, index) in terminalHistory"
        :key="index"
        class="terminal-output"
      >
        <div v-if="entry.command" class="command-line">
          <span class="terminal-prompt">user@83rr-poweredge:~$ </span>
          <span class="command-text">{{ entry.command }}</span>
        </div>
        <div v-if="entry.output === 'CLEAR_SCREEN'" class="clear-marker"></div>
        <div v-else-if="entry.output" class="command-output">
          <pre v-html="formatOutputWithClickableUrls(entry.output)"></pre>
        </div>
      </div>

      <!-- Current input line -->
      <div class="terminal-input-line">
        <span class="terminal-prompt">user@83rr-poweredge:~$ </span>
        <input
          ref="inputElement"
          v-model="currentInput"
          :class="['terminal-input', { 'terminal-input-focused': inputFocused }]"
          type="text"
          @keydown="handleKeydown"
          @input="handleInput"
          @focus="inputFocused = true"
          @blur="inputFocused = false"
          placeholder=""
          autocomplete="off"
          spellcheck="false"
        />
      </div>

      <!-- LinkedIn suggestion -->
      <div v-if="showLinkedinSuggestion && !currentInput" class="suggestion-line">
        <span class="suggestion-text">Try: linkedin (or press Enter)</span>
      </div>
    </div>
  </div>
</template>

<script setup>
const { executeCommand, addToHistory, navigateHistory, currentCommand, getTabCompletion } = useTerminal()

const terminalHistory = ref([])
const currentInput = ref('')
const inputElement = ref(null)
const inputFocused = ref(true)
const showLinkedinSuggestion = ref(true)

// Auto-focus input when component mounts
onMounted(async () => {
  nextTick(() => {
    inputElement.value?.focus()
  })

  // Keep input focused when clicking anywhere on terminal
  document.addEventListener('click', () => {
    inputElement.value?.focus()
  })

  // Auto-run neofetch on page load (hidden from command history)
  await nextTick()
  const neofetchOutput = await executeCommand('neofetch')
  terminalHistory.value.push({
    command: '',
    output: neofetchOutput,
    timestamp: new Date()
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

const formatOutputWithClickableUrls = (text) => {
  // URL regex that matches https:// URLs
  const urlRegex = /(https:\/\/[^\s]+)/g

  // Escape HTML characters first
  const escapedText = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Replace URLs with clickable links
  return escapedText.replace(urlRegex, '<a href="$1" target="_blank" class="terminal-link">$1</a>')
}

const handleInput = () => {
  // Hide LinkedIn suggestion when user starts typing
  if (currentInput.value) {
    showLinkedinSuggestion.value = false
  }
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
      // Empty command - execute linkedin as default
      const output = await executeCommand('linkedin')
      terminalHistory.value.push({
        command: 'linkedin',
        output,
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
    const completed = getTabCompletion(currentInput.value)
    currentInput.value = completed
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

.terminal-input {
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
  margin-left: 8px;
}

.terminal-input-focused {
  caret-color: #ffffff;
}

.suggestion-line {
  margin-top: 5px;
  margin-left: 250px; /* Align with input after prompt */
}

.suggestion-text {
  color: #888;
  font-style: italic;
  font-size: 0.9em;
}

.terminal-link {
  color: inherit;
  text-decoration: none;
  cursor: default;
}

.terminal-link:hover {
  color: #4a9eff;
  text-decoration: underline;
  cursor: pointer;
}
</style>