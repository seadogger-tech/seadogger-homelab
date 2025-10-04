# K8up AWS Infrastructure Setup

## Prerequisites
- AWS Account: 708765384784
- Admin access to AWS Console **OR** AWS CLI with root/admin credentials configured
- `openssl` installed for generating Restic password

## AWS CLI Setup (If Using CLI)

If you want to use AWS CLI instead of the console, you need root/admin credentials configured:

```bash
# Configure AWS CLI with root credentials
aws configure --profile root
# Enter:
#   AWS Access Key ID: <your-root-access-key>
#   AWS Secret Access Key: <your-root-secret-key>
#   Default region: us-east-1
#   Default output format: json

# Verify access
AWS_PROFILE=root aws sts get-caller-identity
```

## Manual Setup Steps

### 1. Create S3 Bucket

```bash
AWS_PROFILE=root aws s3api create-bucket \
  --bucket seadogger-homelab-backup \
  --region us-east-1
```

**Or via AWS Console:**
1. Go to S3 Console
2. Click "Create bucket"
3. Bucket name: `seadogger-homelab-backup`
4. Region: `us-east-1`
5. Click "Create bucket"

### 2. Enable Versioning

```bash
AWS_PROFILE=root aws s3api put-bucket-versioning \
  --bucket seadogger-homelab-backup \
  --versioning-configuration Status=Enabled
```

**Or via AWS Console:**
1. Open bucket `seadogger-homelab-backup`
2. Go to "Properties" tab
3. Find "Bucket Versioning" section
4. Click "Edit"
5. Select "Enable"
6. Click "Save changes"

### 3. Apply Lifecycle Policy (Deep Archive after 1 day)

```bash
AWS_PROFILE=root aws s3api put-bucket-lifecycle-configuration \
  --bucket seadogger-homelab-backup \
  --lifecycle-configuration file://s3-lifecycle-policy.json
```

**Or via AWS Console:**
1. Open bucket `seadogger-homelab-backup`
2. Go to "Management" tab
3. Click "Create lifecycle rule"
4. Rule name: `MoveToDeepArchiveAfter1Day`
5. Choose "Apply to all objects in the bucket"
6. Under "Lifecycle rule actions", select "Transition current versions of objects between storage classes"
7. Days after object creation: `1`
8. Storage class: `Glacier Deep Archive`
9. Click "Create rule"

### 4. Create IAM User

```bash
AWS_PROFILE=root aws iam create-user --user-name k8up-backup-user
```

**Or via AWS Console:**
1. Go to IAM Console
2. Click "Users" in left sidebar
3. Click "Add users"
4. Username: `k8up-backup-user`
5. Click "Next"
6. Select "Attach policies directly"
7. Click "Next" (we'll attach policy in next step)
8. Click "Create user"

### 5. Create and Attach IAM Policy

```bash
AWS_PROFILE=root aws iam create-policy \
  --policy-name K8upBackupPolicy \
  --policy-document file://iam-policy.json

AWS_PROFILE=root aws iam attach-user-policy \
  --user-name k8up-backup-user \
  --policy-arn arn:aws:iam::708765384784:policy/K8upBackupPolicy
```

**Or via AWS Console:**
1. Go to IAM Console
2. Click "Policies" in left sidebar
3. Click "Create policy"
4. Click "JSON" tab
5. Paste contents of `iam-policy.json`
6. Click "Next: Tags"
7. Click "Next: Review"
8. Policy name: `K8upBackupPolicy`
9. Click "Create policy"
10. Go back to "Users" > "k8up-backup-user"
11. Click "Add permissions" > "Attach policies directly"
12. Search for "K8upBackupPolicy"
13. Check the box next to it
14. Click "Add permissions"

### 6. Create Access Keys

```bash
AWS_PROFILE=root aws iam create-access-key --user-name k8up-backup-user
```

**Or via AWS Console:**
1. Go to IAM Console > Users > k8up-backup-user
2. Click "Security credentials" tab
3. Scroll to "Access keys" section
4. Click "Create access key"
5. Select "Third-party service"
6. Check confirmation checkbox
7. Click "Next"
8. Click "Create access key"
9. **SAVE THE ACCESS KEY ID AND SECRET ACCESS KEY** (you won't see the secret again!)

### 7. Generate Restic Encryption Password

```bash
openssl rand -base64 32
```

Save this password securely!

### 8. Update config.yml

Add these three variables to your local `config.yml` file:

```yaml
k8up_aws_access_key: "YOUR_ACCESS_KEY_ID_FROM_STEP_6"
k8up_aws_secret_key: "YOUR_SECRET_ACCESS_KEY_FROM_STEP_6"
k8up_restic_password: "YOUR_RESTIC_PASSWORD_FROM_STEP_7"
```

## Verification

```bash
# Verify bucket exists
AWS_PROFILE=root aws s3 ls s3://seadogger-homelab-backup

# Verify versioning is enabled
AWS_PROFILE=root aws s3api get-bucket-versioning --bucket seadogger-homelab-backup

# Verify lifecycle policy
AWS_PROFILE=root aws s3api get-bucket-lifecycle-configuration --bucket seadogger-homelab-backup

# Verify IAM user
AWS_PROFILE=root aws iam get-user --user-name k8up-backup-user

# Verify policy is attached
AWS_PROFILE=root aws iam list-attached-user-policies --user-name k8up-backup-user
```

## Cost Estimation

- S3 Deep Archive Storage: $0.00099 per GB/month ($1 per TB/month)
- Restore requests: $0.0025 per 1000 requests
- Restore time: 12-48 hours (standard retrieval)
- Estimated monthly cost for 100GB backups: ~$0.10/month
- Estimated monthly cost for 1TB backups: ~$1/month

## Security Notes

- Access keys should NEVER be committed to Git
- config.yml is already in .gitignore
- Restic password encrypts all backup data at rest
- Use different restic password than any other system passwords
