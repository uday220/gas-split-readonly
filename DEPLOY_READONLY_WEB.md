# Publish a read-only web view

This project can generate a static, read-only snapshot for GitHub Pages. The public site has no login, no edit controls, and no database connection. It is a view of the tracker at the moment you generate it.

## Privacy first

The generated `docs/index.html` contains participant names, balances, costs, dates, descriptions, and notes. Anyone with the public website link can read that information. Do not publish it unless everyone is comfortable with that visibility. The local database (`gas_tracker.db`) and original spreadsheet (`407.xlsx`) are excluded by `.gitignore` and must never be uploaded.

GitHub warns that Pages sites are publicly available on the internet, even when a private repository can use Pages under an eligible plan. If this must be visible only to the three of you, use a hosting service with access control instead of this public-pages approach.

## Create the static site

1. Close the desktop app so the snapshot is taken after all current entries are saved.
2. In this project folder, run:

   ```powershell
   py publish_readonly.py
   ```

3. Open `docs/index.html` in a browser to check it. It has only balances and activity; no data can be changed on the page.

## Deploy with GitHub Pages

1. Create a new GitHub repository for the project. Do not add the database or spreadsheet.
2. In PowerShell, from this project folder, create the first commit and push it. Replace the placeholder with your repository URL:

   ```powershell
   git init
   git add gas_tracker.py publish_readonly.py docs README.md DEPLOY_READONLY_WEB.md .gitignore
   git commit -m "Publish read-only Gas Split snapshot"
   git branch -M main
   git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
   git push -u origin main
   ```

3. On GitHub, open the repository's **Settings** > **Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**, select `main`, then select the `/docs` folder, and save.
5. GitHub will show the published URL in the Pages settings. Share that URL only with people who should see the data.

GitHub Pages can publish plain HTML directly from a repository, and it supports selecting the `/docs` folder on a branch as the publishing source. The page entry point must be named `index.html` at the top of that selected folder. See GitHub's official guidance: [What is GitHub Pages?](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [configuring a publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), and [404 troubleshooting](https://docs.github.com/en/pages/getting-started-with-github-pages/troubleshooting-404-errors-for-github-pages-sites).

## Update the published page

Whenever new entries or payments are added in the desktop app:

```powershell
py publish_readonly.py
git add docs/index.html
git commit -m "Update shared-cost snapshot"
git push
```

GitHub Pages republishes when the selected branch/folder changes. GitHub notes that publishing can take up to about ten minutes.

## What this deployment does and does not do

- It does: show a clean, shareable, read-only dashboard in a browser.
- It does not: sync live automatically, accept edits, expose the SQLite database, or replace local backups.
- The desktop app remains the only source of truth. Make changes there, make a backup, regenerate `docs/index.html`, then push the static snapshot.
