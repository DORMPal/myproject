# Build stage
FROM node:20-alpine AS build
# EXPOSE 4200

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
# RUN npm ci --only=production
RUN npm ci 

# Copy source code
COPY . .

# Build the application
# CMD ["npm", "run", "start", "--host", "0.0.0.0"]
# CMD ["ls", "-al"]
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built app from build stage
COPY --from=build /app/dist/frontend /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start nginx
# ENTRYPOINT [ "/bin/sh" ]
ENTRYPOINT ["nginx", "-g", "daemon off;"]