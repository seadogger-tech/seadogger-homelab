# Minecraft Pack Loading Instructions

## For Your Son - Easy Pack Upload

### Step 1: Go to Nextcloud
1. Open **https://nextcloud.seadogger-homelab** in your browser
2. Log in with your Nextcloud account

### Step 2: Navigate to Minecraft Packs Folder
1. Go to **Files**
2. Look for the folder called **`minecraft-packs`**
3. Inside you'll see two folders:
   - **`resource-packs`** - for textures, models, sounds (from Blockbench)
   - **`behavior-packs`** - for gameplay mechanics, custom entities

### Step 3: Upload Your .mcpack File
1. Open the appropriate folder (usually `resource-packs` for Blockbench creations)
2. Click the **Upload** button (+ icon)
3. Select your `.mcpack` file from Blockbench
4. Wait for upload to complete

### Step 4: Wait for Auto-Install
- The pack will **automatically** be extracted to the Minecraft server
- This happens every 5 minutes (check back in ~5 minutes)
- Once processed, the `.mcpack` file will move to a `.processed` folder

### Step 5: Done!
- The pack is now installed on the server
- Restart Minecraft on your Xbox if needed
- The new pack should appear in-game

---

## For Dad - Technical Details

### How It Works
- A CronJob runs every 5 minutes checking for new `.mcpack` files
- Files in `minecraft-packs/resource-packs/` → extracted to `/data/resource_packs/`
- Files in `minecraft-packs/behavior-packs/` → extracted to `/data/behavior_packs/`
- Processed files are moved to `.processed/` folder to avoid re-processing

### Manual Extraction (if needed)
```bash
# Resource pack
kubectl exec -n minecraft-bedrock deployment/minecraft-bedrock -- \
  unzip /data/resource_packs/FILENAME.mcpack -d /data/resource_packs/

# Behavior pack
kubectl exec -n minecraft-bedrock deployment/minecraft-bedrock -- \
  unzip /data/behavior_packs/FILENAME.mcpack -d /data/behavior_packs/
```

### Check CronJob Status
```bash
kubectl get cronjobs -n minecraft-bedrock
kubectl get jobs -n minecraft-bedrock
kubectl logs -n minecraft-bedrock job/minecraft-pack-sync-XXXXX
```

### Restart Server (if packs don't load)
```bash
kubectl rollout restart deployment/minecraft-bedrock -n minecraft-bedrock
```

---

## Xbox Connection

### Method 1: LAN Discovery (Easiest)
1. Open Minecraft Bedrock on Xbox
2. Go to **Play** → **Friends**
3. Scroll to **LAN Games**
4. Look for **"SeaDogger Homelab"**
5. Click to join

### Method 2: Via Mobile/PC First
1. On mobile or Windows 10 Minecraft:
   - Add Server: `192.168.1.247:19132`
   - Name: "SeaDogger Homelab"
2. Connect once from mobile
3. Server will appear on Xbox in Friends/Servers list

---

## Quick Reference

**Nextcloud Upload:** https://nextcloud.seadogger-homelab
**Game Server IP:** 192.168.1.247:19132
**Server Name:** SeaDogger Homelab

**Pack Folders:**
- Resource Packs: `minecraft-packs/resource-packs/`
- Behavior Packs: `minecraft-packs/behavior-packs/`

**Auto-sync:** Every 5 minutes
