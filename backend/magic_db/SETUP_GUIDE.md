# Setup guide: Docker, PostgreSQL, MinIO and magic_db, step by step

This guide assumes you have never used Docker or PostgreSQL. Each step says what to type and what
you should see. It is written for **Windows with Docker inside WSL Ubuntu**, which is your setup.
It takes about 20 minutes the first time.

**What runs where**

- **PostgreSQL** is the database: parties, designs, chats, credits, logins. It runs inside Docker.
- **MinIO** is the image store: photos and outlines. It runs inside Docker too, and later Contabo replaces it.
- **Docker** (inside your WSL Ubuntu) runs both with one command, so you don't install PostgreSQL or MinIO yourself.
- **The backend** (`python api.py`) talks to both of them. The website talks only to the backend.

---

## Step 1. Start Docker (Windows + WSL Ubuntu)

Docker is already installed in your WSL Ubuntu, and `hello-world` works. Every command in this
guide goes in the **Ubuntu (WSL) terminal**, not PowerShell.

1. Start Docker each time you open WSL:
   ```
   sudo service docker start
   ```
2. One time only, so you don't have to type `sudo` before every docker command:
   ```
   sudo usermod -aG docker $USER
   ```
   Then close the Ubuntu window and open it again. Check it with `docker ps` (no sudo). You should
   see an empty list, not "permission denied".
3. One time only, install Python's virtual-environment tool:
   ```
   sudo apt update && sudo apt install -y python3-venv python3-pip
   ```

Tip: keep the project inside WSL, for example `~/projects/magic-outline`, not under
`/mnt/c/...`. Files on `/mnt/c` work, but Python and Docker run much slower there. Your Windows
browser still opens `http://localhost:8000` normally, because WSL shares localhost with Windows.

## Step 2. Put the folder in place

Unzip `magic_db.zip` so the folder sits **inside** the backend folder, next to `api.py`:

```
backend/
  api.py
  sketchclean/
  magic_db/        <- here
```

```
cd ~/projects/magic-outline/backend      # your backend folder
unzip ~/magic_db.zip -d .                # or copy the folder in with Windows Explorer: \\wsl$\Ubuntu\home\<you>
```

From now on, run every command **inside the `backend` folder**.

## Step 3. Start PostgreSQL and MinIO

```
docker compose -f magic_db/docker-compose.yml up -d
```

The first time, this downloads about 300 MB. Then check that both are running:

```
docker compose -f magic_db/docker-compose.yml ps
```

You should see `postgres` and `minio`, both **running** (postgres also says **healthy**).

- They keep running in the background while Docker runs. After a Windows restart, run
  `sudo service docker start`, then this `up -d` command again.
- Stop them: `docker compose -f magic_db/docker-compose.yml down`. Your data is kept.
- Start them again: the same `up -d` command.

## Step 4. Settings (.env)

Open `backend/.env` (create it if it does not exist) and paste in everything from
`magic_db/.env.example`. For your own computer, the values can stay as they are, except:

- `SECRET_KEY`: make one with
  ```
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
  and paste the result.
- For local testing you may set `OTP_DEV_ECHO=1` and `PAYMENTS_MODE=fake`. **Never** set them on the live server.

## Step 5. Install the Python packages

Make a virtual environment once (a private Python folder for this project), then activate it each
time you open a new terminal:

```
python3 -m venv .venv               # once
source .venv/bin/activate           # every new terminal; the prompt starts with (.venv)
pip install -r requirements.txt
pip install -r magic_db/requirements.txt
```

While `(.venv)` shows, `python` means this project's Python. Every command below assumes it.

## Step 6. Create the tables and the image bucket

```
python -m magic_db migrate
python -m magic_db create-bucket
python -m magic_db check
```

You should see:
```
Database is up to date.
Bucket ready: magic-outline
PostgreSQL OK: PostgreSQL 16..., 23 tables
Storage OK: s3 http://127.0.0.1:9000
```

Optional: a demo shop with 2 parties, 1 design and 1 chat:
```
python -m magic_db seed-demo
```
Log in with mobile **9999999999** and password **demo1234**.

## Step 7. Connect it to the backend

In `backend/api.py`, find the line `app = FastAPI(title=...)` and add these two lines right under it:

```python
import magic_db
magic_db.setup(app)
```

Start the backend as usual:
```
python api.py
```

Open **http://127.0.0.1:8000/docs** in the browser. You will see every route, including the new
`/api/auth/register`, `/api/parties` and the rest. You can try them from that page.

## Step 8. Switch the website to the real database

In `frontend/.env.local`, set:
```
NEXT_PUBLIC_USE_MOCKS=0
```
Then restart `npm run dev`. Register a new shop on the website. Parties, designs and chats now
stay saved after a refresh, on any computer.

---

## Looking at the data

**Images (MinIO console):** open http://localhost:9001 and log in with user `magicadmin`, password `magicadmin123`.
Open the `magic-outline` bucket. Files are stored at `acc/<shop id>/designs/<design id>/<image id>/`.

**Tables (PostgreSQL):** the easiest way is a free Windows app such as **DBeaver** (https://dbeaver.io)
or **pgAdmin**. It reaches the database inside WSL through localhost. Make a new PostgreSQL connection with these settings:

| Setting | Value |
|---|---|
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `magic_outline` |
| User | `magic` |
| Password | `magic` |

Or use the terminal:
```
docker compose -f magic_db/docker-compose.yml exec postgres psql -U magic magic_outline
```
Inside it, `\dt` lists tables, `select name, area from parties;` shows parties, and `\q` quits.

## Changing a table later (the ORM way)

1. Edit the class in `magic_db/models.py`, for example to add a column.
2. `python -m magic_db make-migration "add whatsapp to parties"`. This writes a new file in `magic_db/migrations/versions/`. Read it to check it does what you meant.
3. `python -m magic_db migrate`

Never change tables by hand on the live server. Always use a migration, so every computer stays the same.

## Selling plans before Razorpay is connected

When a customer pays you by UPI:
```
python -m magic_db set-plan 9825012345 pro          # starts the month and adds 470 credits
python -m magic_db grant 9825012345 50 --top-up     # 50 extra credits
```

## Going live on the Contabo VPS

1. Install Docker on the VPS (`curl -fsSL https://get.docker.com | sh`).
2. Copy the backend folder there. In `magic_db/docker-compose.yml`, change the passwords
   (`POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`) and use the same ones in `.env`.
3. In `.env`, set a new `SECRET_KEY`, `COOKIE_SECURE=1`, `OTP_DEV_ECHO=0`, `PAYMENTS_MODE=off`, an
   `API_TOKEN`, and an empty `DEV_LOGIN_PHONE`.
4. Run steps 3, 6 and 7 on the VPS.
5. Add two daily jobs (`crontab -e`):
   ```
   0 2 * * *  cd /path/to/backend && python -m magic_db renew-due
   30 2 * * * docker compose -f /path/to/backend/magic_db/docker-compose.yml exec -T postgres pg_dump -U magic magic_outline | gzip > /backups/db-$(date +\%F).sql.gz
   ```
6. **Moving images to Contabo Object Storage later:** create a bucket in the Contabo panel and put its
   endpoint and keys in `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `S3_BUCKET`. No code changes.
   Copy the old files across once with `mc mirror` (MinIO's copy tool).

## When something goes wrong

| You see | What to do |
|---|---|
| `connection refused` on port 5432 or 9000 | Docker is stopped (after a restart). Run `sudo service docker start`, then step 3. |
| `permission denied ... docker.sock` | Run step 1.2 (`usermod`), then close and reopen the Ubuntu window. |
| `port is already allocated` | Another PostgreSQL is installed on your computer. Stop it, or change `127.0.0.1:5432:5432` to `127.0.0.1:5433:5432` in `docker-compose.yml` and use `:5433` in `DATABASE_URL`. |
| `password authentication failed` | `.env` and `docker-compose.yml` have different passwords. If you changed the password after the first start, run `down -v` (this deletes the data) and `up -d` again. |
| `relation "..." does not exist` | Run `python -m magic_db migrate`. |
| `NoSuchBucket` | Run `python -m magic_db create-bucket`. |
| Website says "Please log in again" | Log in again. The login cookie lasts 30 days. Check that the frontend proxy forwards cookies. |
| `No module named magic_db` | Run the command inside the `backend` folder, the one that holds `magic_db/`. |
| Forgot-password code never arrives | No SMS service yet. The code is printed in the `python api.py` window. |
