// Dynamic Island: reports the playing Spotify track to the island, which needs the track id
// to fetch Spicy Lyrics. Install: copy to %APPDATA%\spicetify\Extensions,
// then `spicetify config extensions island.js` and `spicetify apply`.
(function island() {
    // Must match lyrics.spicetify_port in the island's config.json.
    const PORT = 38917;
    // The island may start after Spotify, so the current track is repeated now and then.
    const REPEAT_MS = 10000;

    const player = window.Spicetify && Spicetify.Player;
    if (!player || !player.addEventListener || !player.data) {
        setTimeout(island, 300);
        return;
    }

    function send() {
        const item = player.data && player.data.item;
        if (!item || typeof item.uri !== "string" || !item.uri.startsWith("spotify:track:")) return;
        const duration = (item.duration && item.duration.milliseconds) || (item.metadata && item.metadata.duration) || 0;
        const body = JSON.stringify({ uri: item.uri, title: item.name || "", duration_ms: Number(duration) || 0 });
        // text/plain + no-cors keeps it a simple request without a CORS preflight.
        fetch(`http://127.0.0.1:${PORT}/track`, {
            method: "POST",
            mode: "no-cors",
            headers: { "Content-Type": "text/plain" },
            body,
        }).catch(() => {});
    }

    player.addEventListener("songchange", send);
    setInterval(send, REPEAT_MS);
    send();
})();
