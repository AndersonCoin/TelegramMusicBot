# 🎵 Professional Telegram Music Bot

A high-performance, feature-rich, and modular Telegram music bot built with Pyrogram and PyTgCalls. Designed for seamless music streaming in groups and channels with a focus on user experience, stability, and extensibility.

  <!-- It's highly recommended to add a GIF showcasing the bot -->

## ✨ Features

- **High-Quality Audio:** Stream music directly from YouTube in the best available audio quality.
- **Dynamic Controls:** A beautiful, persistent "Now Playing" message with inline keyboard controls that update in real-time.
- **Multi-Language Support:** Fluent in both **English** and **Arabic (العربية)** with easy language switching.
- **Queue Management:** Add songs to a queue, view upcoming tracks with pagination, and skip songs.
- **Auto Assistant:** The bot automatically invites and manages a helper account to join voice chats, so you don't have to.
- **Auto-Resume:** If the bot restarts or crashes, it automatically resumes playback from where it left off in all active chats.
- **Admin-Only Controls:** Secure your playback controls, allowing only group admins to pause, skip, or stop the music.
- **Modular & Extensible:** Built with a clean plugin-based architecture, making it easy to add new features.
- **Deployment Ready:** Comes with configuration for easy deployment on platforms like Render and Railway.

---

## 🚀 Quick Start & Deployment

### 1. Prerequisites

- **Python 3.11+** installed on your local machine.
- A **Telegram Account** to get API credentials.
- A **second Telegram Account** to act as the music assistant.
- A **Bot Token** from [@BotFather](https://t.me/BotFather).

### 2. Get API Credentials

1.  Go to [my.telegram.org](https://my.telegram.org) and log in with your primary Telegram account.
2.  Navigate to **API development tools**.
3.  Create a new application (you can name it anything).
4.  Copy and save your `API_ID` and `API_HASH`.

### 3. Create a Bot on Telegram

1.  Open Telegram and message [@BotFather](https://t.me/BotFather).
2.  Send `/newbot` and follow the instructions to create your bot.
3.  Copy and save the `BOT_TOKEN` provided.
4.  **(Recommended)** Set a profile picture and description for your bot using `/setuserpic` and `/setdescription`.
5.  **(Important)** Disable group privacy mode to allow the bot to read messages in groups:
    - Send `/mybots` to @BotFather.
    - Select your bot.
    - Go to **Bot Settings** -> **Group Privacy** -> **Turn off**.

### 4. Generate Session String

The bot uses a second Telegram account (the "assistant") to stream audio. You need to generate a `SESSION_STRING` for this account.

1.  Clone this repository to your local machine:
    ```bash
    git clone https://github.com/YourUsername/YourRepoName.git
    cd YourRepoName
    ```
2.  Install the necessary dependencies:
    ```bash
    pip install pyrogram TgCrypto
    ```
3.  Run the session generator script:
    ```bash
    python generate_session.py
    ```
4.  Follow the prompts:
    -   Enter the `API_ID` and `API_HASH` you got in Step 2.
    -   Enter the **phone number of your assistant account**.
    -   Enter the login code sent to that account.
    -   If you have 2FA enabled, enter your password.
5.  Copy the generated `SESSION_STRING` and save it securely.

### 5. Configuration

1.  Create a file named `.env` in the root of the project.
2.  Copy the contents of `.env.example` into it.
3.  Fill in the values with your credentials:

    ```env
    # From my.telegram.org
    API_ID=...
    API_HASH=...

    # From @BotFather
    BOT_TOKEN=...

    # From generate_session.py
    SESSION_STRING=...

    # The username of your assistant account (without @)
    ASSISTANT_USERNAME=...
    ```

### 6. Deployment

#### Method A: Deploy on Render (Recommended)

1.  **Fork this repository** on GitHub.
2.  Go to the [Render Dashboard](https://dashboard.render.com/) and create a **New Web Service**.
3.  Connect your forked GitHub repository.
4.  Set the following configuration:
    -   **Environment:** Python
    -   **Build Command:** `pip install -r requirements.txt`
    -   **Start Command:** `python app.py`
5.  Go to the **Environment** tab and add the following **Environment Variables** (do not use a `.env` file here):
    -   `API_ID`
    -   `API_HASH`
    -   `BOT_TOKEN`
    -   `SESSION_STRING`
    -   `ASSISTANT_USERNAME`
6.  Click **Create Web Service**. Your bot will be live in a few minutes!

#### Method B: Local Testing

To run the bot on your own machine for development or testing:

1.  Make sure you have completed steps 1-5.
2.  Install all dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the bot:
    ```bash
    python app.py
    ```

---

## 🎵 How to Use the Bot in a Group

1.  **Add the Bot:** Invite your main bot (e.g., `@YourMusicBot`) to your Telegram group.
2.  **Make it Admin:** Promote the bot to an administrator with the following permissions:
    -   `Invite Users`
    -   `Add Admins`
    -   (Optional but recommended) `Delete Messages` and `Manage Video Chats`.
3.  **Start a Voice Chat** in the group.
4.  **Play a Song:** Type `/play <song name or YouTube URL>`.
    -   The bot will automatically invite and promote its assistant account.
    -   The assistant will join the voice chat and start streaming the music.
    -   A "Now Playing" message with inline controls will appear.

---

## 🛠️ Available Commands

- `/start` or `/help`: Shows the help menu.
- `/play <query>`: Plays a song from YouTube or adds it to the queue.
- `/pause`: Pauses the current track.
- `/resume`: Resumes the current track.
- `/skip`: Skips the current track and plays the next one.
- `/stop`: Stops playback, clears the queue, and leaves the voice chat.
- `/queue`: Shows the current song and the upcoming tracks.
- `/language`: Allows you to switch the bot's language between English and Arabic.

---

## 🤝 Contributing

Contributions are welcome! If you'd like to improve the bot or add new features, please follow these steps:

1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/YourFeature`).
3.  Make your changes.
4.  Commit your changes (`git commit -m 'Add some feature'`).
5.  Push to the branch (`git push origin feature/YourFeature`).
6.  Open a Pull Request.

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
