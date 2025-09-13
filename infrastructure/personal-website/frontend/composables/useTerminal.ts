export const useTerminal = () => {
  const history = ref<string[]>([])
  const currentCommand = ref('')
  const historyIndex = ref(-1)

  const commands = {
    help: {
      description: 'Show available commands',
      action: () => `Available commands:

help                    Show this help message
clear                   Clear terminal screen
neofetch               Show system information
whoami                 Display user information
ls                     List available services
linkedin               Open LinkedIn profile
github                 Open GitHub profile
services               List all public services
infrastructure         List infrastructure services
weather                Check weather in Ashland, MA
home                   Open Home Assistant
jupyter                Open JupyterHub
about                  About Mark Cheli
contact                Contact information
exit                   Exit terminal

Use 'help <command>' for more information about a specific command.`
    },

    clear: {
      description: 'Clear the terminal screen',
      action: () => 'CLEAR_SCREEN'
    },

    neofetch: {
      description: 'Display system information',
      action: () => `
     ██████╗  ███████╗ ██╗   ██╗
     ██╔══██╗ ██╔════╝ ██║   ██║
     ██║  ██║ █████╗   ██║   ██║
     ██║  ██║ ██╔══╝   ╚██╗ ██╔╝
     ██████╔╝ ███████╗  ╚████╔╝
     ╚═════╝  ╚══════╝   ╚═══╝

     Mark Cheli | Developer
     ────────────────────────────────────────
     OS: Ubuntu 24.04 LTS
     Host: Dell PowerEdge R630
     Kernel: 5.15.0-91-generic
     Shell: Interactive Terminal
     CPU: Intel Xeon (16 cores)
     Memory: 64GB DDR4
     ────────────────────────────────────────
     Services: 6 running
     Infrastructure: Operational
     ────────────────────────────────────────`
    },

    whoami: {
      description: 'Display current user information',
      action: () => `mark-cheli
Developer | Software Engineer | Infrastructure Enthusiast
Location: Ashland, MA
Status: Building cool things`
    },

    ls: {
      description: 'List available services',
      action: () => `total 6
drwxr-xr-x  2 mark users  4096 Dec 13 12:00 public-services/
drwxr-xr-x  2 mark users  4096 Dec 13 12:00 infrastructure/
-rw-r--r--  1 mark users   256 Dec 13 12:00 profile.json
-rw-r--r--  1 mark users   128 Dec 13 12:00 weather.api
-rw-r--r--  1 mark users   512 Dec 13 12:00 links.txt
-rw-r--r--  1 mark users    64 Dec 13 12:00 contact.info

Use 'services' to view public services or 'infrastructure' to view internal services.`
    },

    about: {
      description: 'About Mark Cheli',
      action: () => `Mark Cheli - Developer & Infrastructure Engineer

I'm a passionate developer who loves building robust systems and
exploring new technologies. My homelab infrastructure demonstrates
my commitment to automation, monitoring, and reliable service delivery.

Key interests:
• Full-stack development
• Infrastructure automation
• Container orchestration
• Data science and analytics
• Smart home integration

This terminal interface showcases some of my public services and
provides a glimpse into my infrastructure setup. Feel free to
explore the various commands and services!`
    },

    contact: {
      description: 'Contact information',
      action: () => `Contact Information:

Professional:
  LinkedIn: https://www.linkedin.com/in/mark-cheli-0354a163/
  GitHub: https://github.com/MCheli

Services:
  Personal Website: https://www.markcheli.com
  Development Environment: https://jupyter.ops.markcheli.com
  Smart Home: https://home.markcheli.com

Infrastructure:
  All services are self-hosted on my homelab infrastructure
  Built with Docker, Traefik, and modern DevOps practices`
    }
  }

  const actionCommands = {
    linkedin: () => window.open('https://www.linkedin.com/in/mark-cheli-0354a163/', '_blank'),
    github: () => window.open('https://github.com/MCheli', '_blank'),
    home: () => window.open('https://home.markcheli.com', '_blank'),
    jupyter: () => window.open('https://jupyter.ops.markcheli.com', '_blank'),
  }

  const executeCommand = async (command: string): Promise<string> => {
    const cmd = command.toLowerCase().trim()

    if (commands[cmd]) {
      const result = commands[cmd].action()
      return result
    }

    if (actionCommands[cmd]) {
      actionCommands[cmd]()
      return `Opening ${cmd}...`
    }

    if (cmd === 'services') {
      return `Public Services hosted on markcheli.com:

www.markcheli.com      Interactive terminal website
flask.markcheli.com    Flask API server with weather data
home.markcheli.com     Home Assistant automation platform

Additional Services:
jupyter.ops.markcheli.com  JupyterHub data science environment

Type a service name to open it, or 'linkedin' to connect professionally.`
    }

    if (cmd === 'infrastructure') {
      try {
        const { data } = await $fetch('/api/profile')
        const services = data.services.infrastructure
        let output = 'Infrastructure Services (LAN-only):\n\n'
        services.forEach(service => {
          output += `${service.name.padEnd(20)} ${service.description}\n`
          output += `${' '.repeat(20)} URL: ${service.url}\n\n`
        })
        output += '\nNote: Infrastructure services are only accessible from local network'
        return output
      } catch (error) {
        return 'Error: Unable to fetch infrastructure information'
      }
    }

    if (cmd === 'weather') {
      try {
        const data = await $fetch('/api/weather')
        return `Weather in ${data.location}:

Temperature: ${data.temperature}°F (feels like ${data.feels_like}°F)
Conditions: ${data.description}
Humidity: ${data.humidity}%
Wind Speed: ${data.wind_speed} mph

Data source: ${data.source}
Last updated: ${new Date(data.timestamp).toLocaleString()}`
      } catch (error) {
        return 'Error: Unable to fetch weather information'
      }
    }

    if (cmd === 'exit') {
      return 'Thanks for visiting! Feel free to explore my services.'
    }

    // Check if it's a help command for specific command
    if (cmd.startsWith('help ')) {
      const helpCmd = cmd.substring(5)
      if (commands[helpCmd]) {
        return `${helpCmd}: ${commands[helpCmd].description}`
      }
      return `Unknown command: ${helpCmd}`
    }

    return `Command not found: ${command}

Type 'help' to see available commands.`
  }

  const addToHistory = (command: string) => {
    if (command.trim() && history.value[history.value.length - 1] !== command) {
      history.value.push(command)
    }
    historyIndex.value = -1
  }

  const navigateHistory = (direction: 'up' | 'down') => {
    if (direction === 'up' && historyIndex.value < history.value.length - 1) {
      historyIndex.value++
    } else if (direction === 'down' && historyIndex.value > -1) {
      historyIndex.value--
    }

    if (historyIndex.value >= 0) {
      currentCommand.value = history.value[history.value.length - 1 - historyIndex.value]
    } else {
      currentCommand.value = ''
    }
  }

  return {
    history,
    currentCommand,
    executeCommand,
    addToHistory,
    navigateHistory,
    commands: Object.keys(commands)
  }
}