function getDeviceId() {
    let id = localStorage.getItem("device_id");

    if (!id) {
        id = "dev-" + Math.random().toString(36).substring(2) + Date.now();
        localStorage.setItem("device_id", id);
    }

    return id;
}

document.addEventListener("DOMContentLoaded", () => {

    // =============================
    // EXISTING TRENDING TOGGLE (UNCHANGED)
    // =============================
    const btn = document.getElementById("toggleTrending");
    const grid = document.getElementById("postGrid");

    if (btn && grid) {
        btn.addEventListener("click", () => {
            grid.classList.toggle("trending");

            if (grid.classList.contains("trending")) {
                document.body.style.filter = "saturate(1.1)";
            } else {
                document.body.style.filter = "none";
            }
        });
    }

    // =============================
    // POST PAGE LOGIC (FIXED)
    // =============================

    const postContainer = document.querySelector(".comments");

    if (postContainer) {

        const slug = postContainer.dataset.slug;

        let sessionId = null;
        let startTime = Date.now();

        // -----------------------------
        // TRACK VIEW ✅ FIXED
        // -----------------------------
        fetch(`/track/view/${slug}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                device_id: getDeviceId()
            })
        })
            .then(res => res.json())
            .then(data => {
                sessionId = data.session_id; // 🔥 CRITICAL FIX
            })
            .catch(err => console.error("View tracking error:", err));

        // -----------------------------
        // TRACK TIME SPENT ✅ IMPROVED
        // -----------------------------
        function sendTime() {
            if (!sessionId) return;

            const duration = Math.floor((Date.now() - startTime) / 1000);

            navigator.sendBeacon("/track/time", JSON.stringify({
                session_id: sessionId,
                duration: duration
            }));
        }

        window.addEventListener("beforeunload", sendTime);
        window.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") {
                sendTime();
            }
        });

        // -----------------------------
        // LIKE BUTTON (FIXED)
        // -----------------------------
        const likeBtn = document.getElementById("likeBtn");

        if (likeBtn) {
            likeBtn.addEventListener("click", () => {

                fetch(`/track/like/${slug}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        device_id: getDeviceId()
                    })
                })
                    .then(res => res.json())
                    .then(data => {
                        const likeCount = document.getElementById("likeCount");
                        if (likeCount) likeCount.innerText = data.likes;
                    })
                    .catch(err => console.error("Like error:", err));

            });
        }

        // -----------------------------
        // SHARE BUTTONS (FIXED)
        // -----------------------------
        const shareButtons = document.querySelectorAll(".share-btn");

        shareButtons.forEach(btn => {
            btn.addEventListener("click", () => {

                const platform = btn.dataset.platform;
                const url = window.location.href;

                // 🔥 REAL SHARE
                if (platform === "twitter") {
                    window.open(`https://twitter.com/intent/tweet?url=${url}`);
                }
                if (platform === "linkedin") {
                    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${url}`);
                }

                // 🔥 TRACK
                fetch(`/track/share/${slug}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        platform: platform,
                        device_id: getDeviceId()
                    })
                })
                    .then(res => res.json())
                    .then(data => {
                        const shareCount = document.getElementById("shareCount");
                        if (shareCount) shareCount.innerText = data.shares;
                    })
                    .catch(err => console.error("Share error:", err));

            });
        });

    }

});