#!/usr/bin/env bash
# deploy.sh — provision Azure infra and deploy promptify-concrete-tracker
# Usage: bash scripts/deploy.sh
# Prerequisites: az login, docker, az acr login
set -euo pipefail

# ── Config — edit these if needed ─────────────────────────────────────────────
RG="scanbeton-promptify-rg"
LOCATION="francecentral"
ACR_NAME="scanbetonpromptify"
STORAGE_NAME="scanbetonpromptify"
PG_SERVER="scanbeton-promptify-pg"
PG_DB="promptify"
PG_USER="promptify"
PG_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)Pp1!"   # auto-generated
PLAN_NAME="scanbeton-promptify-plan"
APP_NAME="scanbeton-promptify"
IMAGE_TAG="latest"

# Read secrets from local .env
source .env

# ── 1. Resource group ──────────────────────────────────────────────────────────
echo "==> Creating resource group $RG in $LOCATION..."
az group create --name "$RG" --location "$LOCATION" --output none

# ── 2. Container Registry ─────────────────────────────────────────────────────
echo "==> Creating ACR $ACR_NAME..."
az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --output none

ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

# ── 3. Build & push image ──────────────────────────────────────────────────────
echo "==> Building and pushing Docker image to $ACR_LOGIN_SERVER..."
az acr build \
  --registry "$ACR_NAME" \
  --image "promptify:$IMAGE_TAG" \
  --file docker/Dockerfile \
  .

# ── 4. PostgreSQL Flexible Server ─────────────────────────────────────────────
echo "==> Creating PostgreSQL Flexible Server $PG_SERVER..."
az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --location "$LOCATION" \
  --admin-user "$PG_USER" \
  --admin-password "$PG_PASS" \
  --sku-name "Standard_B1ms" \
  --tier "Burstable" \
  --storage-size 32 \
  --version 16 \
  --public-access "None" \
  --output none

echo "==> Creating database $PG_DB..."
az postgres flexible-server db create \
  --resource-group "$RG" \
  --server-name "$PG_SERVER" \
  --database-name "$PG_DB" \
  --output none

# Allow App Service outbound IPs (set to 0.0.0.0 for now; lock down after deploy)
echo "==> Opening PostgreSQL firewall for initial deploy..."
az postgres flexible-server firewall-rule create \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --rule-name "AllowAll-temp" \
  --start-ip-address "0.0.0.0" \
  --end-ip-address "255.255.255.255" \
  --output none

PG_HOST="${PG_SERVER}.postgres.database.azure.com"
DATABASE_URL="postgresql+psycopg://${PG_USER}:${PG_PASS}@${PG_HOST}/${PG_DB}?sslmode=require"

# ── 5. Storage Account ─────────────────────────────────────────────────────────
echo "==> Creating Storage Account $STORAGE_NAME..."
az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output none

STORAGE_CONN_STR=$(az storage account show-connection-string \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --query connectionString -o tsv)

echo "==> Creating blob containers..."
az storage container create --name "documents" --connection-string "$STORAGE_CONN_STR" --output none
az storage container create --name "datasets"  --connection-string "$STORAGE_CONN_STR" --output none

# ── 6. App Service Plan ────────────────────────────────────────────────────────
echo "==> Creating App Service Plan $PLAN_NAME (B2 Linux)..."
az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --is-linux \
  --sku B2 \
  --output none

# ── 7. Web App ─────────────────────────────────────────────────────────────────
echo "==> Creating Web App $APP_NAME..."
az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --name "$APP_NAME" \
  --deployment-container-image-name "${ACR_LOGIN_SERVER}/promptify:${IMAGE_TAG}" \
  --output none

# Configure ACR credentials for the webapp
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --docker-registry-server-url "https://${ACR_LOGIN_SERVER}" \
  --docker-registry-server-user "$ACR_NAME" \
  --docker-registry-server-password "$ACR_PASSWORD" \
  --output none

# ── 8. App Settings (env vars) ────────────────────────────────────────────────
echo "==> Configuring App Settings..."
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings \
    DATABASE_URL="$DATABASE_URL" \
    AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONN_STR" \
    BLOB_CONTAINER_DOCUMENTS="documents" \
    BLOB_CONTAINER_DATASETS="datasets" \
    AZURE_MISTRALOCR_ENDPOINT="$AZURE_MISTRALOCR_ENDPOINT" \
    AZURE_MISTRALOCR_API_KEY="$AZURE_MISTRALOCR_API_KEY" \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="$AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT" \
    AZURE_DOCUMENT_INTELLIGENCE_KEY="$AZURE_DOCUMENT_INTELLIGENCE_KEY" \
    AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
    AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
    AZURE_OPENAI_DEPLOYMENT_NAME="$AZURE_OPENAI_DEPLOYMENT_NAME" \
    AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
    SEED_ON_STARTUP="true" \
    LOG_LEVEL="INFO" \
    WEBSITES_PORT="8501" \
  --output none

# ── 9. Always-on + startup ────────────────────────────────────────────────────
az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --always-on true \
  --output none

# ── 10. Save credentials to .env.azure for reference ─────────────────────────
cat > .env.azure <<EOF
# Auto-generated by deploy.sh — DO NOT COMMIT
DATABASE_URL=$DATABASE_URL
PG_SERVER=$PG_HOST
PG_USER=$PG_USER
PG_PASS=$PG_PASS
STORAGE_ACCOUNT=$STORAGE_NAME
APP_NAME=$APP_NAME
ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER
APP_URL=https://${APP_NAME}.azurewebsites.net
EOF

echo ""
echo "✅ Deployment complete!"
echo "   App URL : https://${APP_NAME}.azurewebsites.net"
echo "   Postgres: $PG_HOST"
echo "   ACR     : $ACR_LOGIN_SERVER"
echo "   Credentials saved to .env.azure (git-ignored)"
echo ""
echo "   First startup will run 'alembic upgrade head' and seed the dataset."
echo "   Tail logs with:  az webapp log tail -g $RG -n $APP_NAME"
