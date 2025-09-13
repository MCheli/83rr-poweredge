import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { useTerminal } from '~/composables/useTerminal'

// Mock the global $fetch
global.$fetch = vi.fn()

describe('useTerminal', () => {
  const { executeCommand, addToHistory, navigateHistory, history, currentCommand } = useTerminal()

  beforeEach(() => {
    history.value = []
    currentCommand.value = ''
    vi.clearAllMocks()
  })

  it('should execute help command', async () => {
    const result = await executeCommand('help')
    expect(result).toContain('Available commands:')
    expect(result).toContain('help')
    expect(result).toContain('clear')
    expect(result).toContain('neofetch')
  })

  it('should execute clear command', async () => {
    const result = await executeCommand('clear')
    expect(result).toBe('CLEAR_SCREEN')
  })

  it('should execute neofetch command', async () => {
    const result = await executeCommand('neofetch')
    expect(result).toContain('Mark Cheli | Developer')
    expect(result).toContain('OS: Ubuntu 24.04 LTS')
    expect(result).toContain('Services:')
  })

  it('should execute whoami command', async () => {
    const result = await executeCommand('whoami')
    expect(result).toContain('mark-cheli')
    expect(result).toContain('Developer')
    expect(result).toContain('Ashland, MA')
  })

  it('should execute ls command', async () => {
    const result = await executeCommand('ls')
    expect(result).toContain('public-services/')
    expect(result).toContain('infrastructure/')
    expect(result).toContain('profile.json')
  })

  it('should execute about command', async () => {
    const result = await executeCommand('about')
    expect(result).toContain('Mark Cheli - Developer')
    expect(result).toContain('Infrastructure Engineer')
    expect(result).toContain('Key interests:')
  })

  it('should execute contact command', async () => {
    const result = await executeCommand('contact')
    expect(result).toContain('Contact Information:')
    expect(result).toContain('LinkedIn:')
    expect(result).toContain('GitHub:')
  })

  it('should handle unknown commands', async () => {
    const result = await executeCommand('unknown_command')
    expect(result).toContain('Command not found: unknown_command')
    expect(result).toContain("Type 'help' to see available commands")
  })

  it('should execute weather command with API', async () => {
    const mockWeatherData = {
      location: 'Ashland, MA',
      temperature: 72,
      feels_like: 75,
      humidity: 65,
      description: 'Partly Cloudy',
      wind_speed: 8,
      timestamp: new Date().toISOString(),
      source: 'Demo Data'
    }

    global.$fetch.mockResolvedValue(mockWeatherData)

    const result = await executeCommand('weather')
    expect(result).toContain('Weather in Ashland, MA:')
    expect(result).toContain('Temperature: 72°F')
    expect(result).toContain('Conditions: Partly Cloudy')
    expect(result).toContain('Humidity: 65%')
    expect(result).toContain('Wind Speed: 8 mph')
  })

  it('should execute services command with API', async () => {
    const mockProfileData = {
      data: {
        services: {
          public: [
            {
              name: 'JupyterHub',
              url: 'https://jupyter.ops.markcheli.com',
              description: 'Data Science Environment'
            },
            {
              name: 'Home Assistant',
              url: 'https://home.markcheli.com',
              description: 'Smart Home Control'
            }
          ]
        }
      }
    }

    global.$fetch.mockResolvedValue(mockProfileData)

    const result = await executeCommand('services')
    expect(result).toContain('Public Services:')
    expect(result).toContain('JupyterHub')
    expect(result).toContain('Home Assistant')
    expect(result).toContain('https://jupyter.ops.markcheli.com')
  })

  it('should execute infrastructure command with API', async () => {
    const mockProfileData = {
      data: {
        services: {
          infrastructure: [
            {
              name: 'Portainer',
              url: 'https://portainer-local.ops.markcheli.com',
              description: 'Container Management (LAN)'
            }
          ]
        }
      }
    }

    global.$fetch.mockResolvedValue(mockProfileData)

    const result = await executeCommand('infrastructure')
    expect(result).toContain('Infrastructure Services (LAN-only):')
    expect(result).toContain('Portainer')
    expect(result).toContain('Container Management (LAN)')
    expect(result).toContain('only accessible from local network')
  })

  it('should handle API errors gracefully', async () => {
    global.$fetch.mockRejectedValue(new Error('API Error'))

    const weatherResult = await executeCommand('weather')
    expect(weatherResult).toContain('Error: Unable to fetch weather information')

    const servicesResult = await executeCommand('services')
    expect(servicesResult).toContain('Error: Unable to fetch services information')
  })

  it('should add commands to history', () => {
    addToHistory('help')
    addToHistory('neofetch')
    addToHistory('clear')

    expect(history.value).toEqual(['help', 'neofetch', 'clear'])
  })

  it('should not add duplicate consecutive commands to history', () => {
    addToHistory('help')
    addToHistory('help')  // Should not be added
    addToHistory('neofetch')

    expect(history.value).toEqual(['help', 'neofetch'])
  })

  it('should navigate history correctly', () => {
    addToHistory('first')
    addToHistory('second')
    addToHistory('third')

    // Navigate up
    navigateHistory('up')
    expect(currentCommand.value).toBe('third')

    navigateHistory('up')
    expect(currentCommand.value).toBe('second')

    navigateHistory('up')
    expect(currentCommand.value).toBe('first')

    // Navigate down
    navigateHistory('down')
    expect(currentCommand.value).toBe('second')

    navigateHistory('down')
    expect(currentCommand.value).toBe('third')

    navigateHistory('down')
    expect(currentCommand.value).toBe('')
  })

  it('should provide help for specific commands', async () => {
    const result = await executeCommand('help neofetch')
    expect(result).toContain('neofetch: Display system information')

    const unknownResult = await executeCommand('help unknown')
    expect(unknownResult).toContain('Unknown command: unknown')
  })

  it('should execute exit command', async () => {
    const result = await executeCommand('exit')
    expect(result).toContain('Thanks for visiting!')
    expect(result).toContain('explore my services')
  })
})