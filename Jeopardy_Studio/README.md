# Jeopardy Studio

A dependency-free Python web app for creating, saving, editing and playing reusable Jeopardy-style boards.

## Run it

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run:

   ```bash
   python app.py
   ```

4. Open <http://127.0.0.1:8000> in a browser.

No `pip install` is needed. Games and uploaded media are saved locally in `data/`.

## Features

- Automatically generate a board from contestant, category and question counts
- Unlimited saved games, duplication and later editing
- Portable `.jeopardy.json` backups that can be exported and imported later
- Exported backups include attached images, audio and video
- Question and answer text
- Image, audio and video attachments on either side of a clue
- Responsive editing and play modes
- Persistent scores and used-clue state
- Correct/incorrect scoring, active contestant selection and board reset
- Manual in-game score editing with exact-score and adjustment controls
- Full-width Final Jeopardy clue with the same reveal and scoring controls as regular questions
- Full-screen presentation mode
- SQLite storage with no external service or paid API

## Backups

Use **Export** or **Save backup** in the app to download a portable
`.jeopardy.json` file. The backup includes the complete board, contestants,
scores, used-clue state and all attached media. Choose **Import game** to restore
it later, including on another computer running Jeopardy Studio.

For a full installation-level backup, you can also copy the entire `data`
folder. The SQLite database and media uploads are both kept there.

## Hosting on your network

To let devices on the same Wi-Fi open the board, start it with:

```bash
HOST=0.0.0.0 python app.py
```

Then use the computer's local IP address, for example `http://192.168.1.20:8000`.
