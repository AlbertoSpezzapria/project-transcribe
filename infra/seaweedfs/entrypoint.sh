#!/bin/sh
# Genera la configurazione S3 dalle variabili d'ambiente (nessuna credenziale nel repo).
set -eu
cat > /tmp/s3.json <<JSON
{
  "identities": [
    {
      "name": "redazione-api",
      "credentials": [{ "accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}" }],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    }
  ]
}
JSON
exec weed server -dir=/data -ip=storage -ip.bind=0.0.0.0 \
  -s3 -s3.port=8333 -s3.config=/tmp/s3.json \
  -master.volumeSizeLimitMB=1024 -volume.max=0
