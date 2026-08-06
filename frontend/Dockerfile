# frontend/Dockerfile
FROM node:18-alpine

WORKDIR /app

# Copia i file di configurazione
COPY package*.json ./

# Installa le dipendenze
RUN npm install --legacy-peer-deps

# Copia il codice sorgente
COPY . .

# Espone la porta di Next.js
EXPOSE 3000

ENV HOST=0.0.0.0
ENV PORT=3000

# Avvia in modalità sviluppo con live reload
CMD ["npm", "run", "dev"]