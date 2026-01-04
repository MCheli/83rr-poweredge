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
whoami                  Display user information
ls                      List available services
linkedin                Open LinkedIn profile
github                  Open GitHub profile
services                List all services and infrastructure
weather                 Check weather in Ashland, MA
cookbook                Open recipe cookbook
home                    Open Home Assistant
jupyter                 Open JupyterHub
minecraft               Open Minecraft server status
about                   About Mark Cheli
contact                 Contact information
exit                    Exit terminal

Use 'help <command>' for more information about a specific command.`
    },

    clear: {
      description: 'Clear the terminal screen',
      action: () => 'CLEAR_SCREEN'
    },

    neofetch: {
      description: 'Display system information',
      action: () => `
     ███╗   ███╗ █████╗ ██████╗ ██╗  ██╗
     ████╗ ████║██╔══██╗██╔══██╗██║ ██╔╝
     ██╔████╔██║███████║██████╔╝█████╔╝
     ██║╚██╔╝██║██╔══██║██╔══██╗██╔═██╗
     ██║ ╚═╝ ██║██║  ██║██║  ██║██║  ██╗
     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

      ██████╗██╗  ██╗███████╗██╗     ██╗
     ██╔════╝██║  ██║██╔════╝██║     ██║
     ██║     ███████║█████╗  ██║     ██║
     ██║     ██╔══██║██╔══╝  ██║     ██║
     ╚██████╗██║  ██║███████╗███████╗██║
      ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝

     Development | Engineering | Strategy | Data Analysis | Operations
     ────────────────────────────────────────
     OS: Ubuntu 24.04 LTS
     Host: Dell PowerEdge R630
     Kernel: 5.15.0-91-generic
     CPU: Intel Xeon (16 cores)
     Memory: 128GB DDR4
     ────────────────────────────────────────
     Services: 10/10 running
     Status: Operational
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

Use 'services' to view all available services and infrastructure.`
    },

    about: {
      description: 'About Mark Cheli',
      action: () => `Mark Cheli - Product Strategist & Engineering Leader

A developer-turned-product strategist with a passion for the cross-functional
journey of bringing innovative products to market. I thrive at the intersection
of engineering and business strategy, leading initiatives that bridge technical
and go-to-market teams.

Professional Focus:
• Product-led growth strategies for technical products
• Cross-functional team leadership (R&D, PM, UX, Sales, Marketing)
• Viral product adoption and user engagement
• MCAD and EdTech product development
• Engineering management and team scaling

Background:
• Experience with PTC's product ecosystem (Onshape, Creo, Windchill, ThingWorx)
• Full-stack development
• Self-hosted infrastructure enthusiast
`
    },

    contact: {
      description: 'Contact information',
      action: () => `Contact Information:

Professional:
  LinkedIn: https://www.linkedin.com/in/mark-cheli-0354a163/
  GitHub: https://github.com/MCheli

Services:
  Personal Website: https://www.markcheli.com
  Cookbook: https://cookbook.markcheli.com
  API Server: https://flask.markcheli.com
  Development Environment: https://jupyter.markcheli.com
  Smart Home: https://home.markcheli.com
  Minecraft Server: minecraft.markcheli.com:25565

Infrastructure:
  All services are self-hosted on my homelab infrastructure
  Built with Docker, NGINX, and modern DevOps practices`
    }
  }

  const actionCommands = {
    linkedin: () => window.open('https://www.linkedin.com/in/mark-cheli-0354a163/', '_blank'),
    github: () => window.open('https://github.com/MCheli', '_blank'),
    cookbook: () => window.open('https://cookbook.markcheli.com', '_blank'),
    home: () => window.open('https://home.markcheli.com', '_blank'),
    jupyter: () => window.open('https://jupyter.markcheli.com', '_blank'),
    minecraft: () => window.open('https://minecraft.markcheli.com', '_blank'),
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
      return `Public Services (Internet accessible):

https://www.markcheli.com       Interactive terminal website
https://cookbook.markcheli.com  Recipe cookbook & meal planner
https://flask.markcheli.com     Flask API server with weather data
https://jupyter.markcheli.com   JupyterHub data science environment
https://home.markcheli.com      Home Assistant smart home platform
minecraft.markcheli.com:25565   Minecraft Java Edition server

Internal Infrastructure (LAN-only):

https://logs-local.ops.markcheli.com        OpenSearch Dashboards log aggregation
https://opensearch-local.ops.markcheli.com  OpenSearch API and cluster management

System Monitoring (LAN-only):

https://grafana-local.ops.markcheli.com    Grafana system dashboards & metrics
https://prometheus-local.ops.markcheli.com Prometheus metrics database
https://cadvisor-local.ops.markcheli.com   cAdvisor container monitoring

Type a service name to open it, or 'linkedin' to connect professionally.`
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

  const getCommandCompletions = (partial: string): string[] => {
    const allCommands = [...Object.keys(commands), ...Object.keys(actionCommands), 'services', 'weather', 'exit']
    return allCommands.filter(cmd => cmd.startsWith(partial.toLowerCase()))
  }

  const getTabCompletion = (input: string): string => {
    const parts = input.trim().split(' ')
    const partial = parts[parts.length - 1]

    if (parts.length === 1) {
      const completions = getCommandCompletions(partial)
      if (completions.length === 1) {
        return completions[0]
      } else if (completions.length > 1) {
        // Return the longest common prefix
        return completions.reduce((acc, cmd) => {
          let i = 0
          while (i < acc.length && i < cmd.length && acc[i] === cmd[i]) {
            i++
          }
          return acc.substring(0, i)
        })
      }
    }

    return input
  }

  return {
    history,
    currentCommand,
    executeCommand,
    addToHistory,
    navigateHistory,
    getTabCompletion,
    commands: Object.keys(commands)
  }
}