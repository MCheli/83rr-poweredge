FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production image
FROM node:18-alpine AS runner

WORKDIR /app

# Install curl and create non-root user
RUN apk add --no-cache curl && \
    addgroup -g 1001 -S nodejs && \
    adduser -S nuxtjs -u 1001

# Copy built application
COPY --from=builder --chown=nuxtjs:nodejs /app/.output /app/.output

# Create symlink for Nuxt SSR static assets
# Nuxt server looks for static files in server/chunks/public but they're in public
RUN mkdir -p /app/.output/server/chunks/public && \
    ln -sf /app/.output/public/_nuxt /app/.output/server/chunks/public/_nuxt

USER nuxtjs

EXPOSE 3000

ENV PORT=3000
ENV HOST=0.0.0.0
ENV NODE_ENV=production

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

CMD ["node", ".output/server/index.mjs"]