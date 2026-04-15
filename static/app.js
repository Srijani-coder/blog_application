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

    // 🔥 IMPORTANT: do NOT return here
    if (postContainer) {

        const slug = postContainer.dataset.slug;

        let sessionId = null;
        let startTime = Date.now();

        // -----------------------------
        // TRACK VIEW
        // -----------------------------
        fetch(`/track/view/${slug}`, {
            method: "POST"
        })
            .then(res => res.json())
            .then(data => {
                sessionId = data.session_id;
            })
            .catch(err => console.error("View tracking error:", err));

        // -----------------------------
        // TRACK TIME SPENT
        // -----------------------------
        window.addEventListener("beforeunload", () => {
            if (!sessionId) return;

            const duration = Math.floor((Date.now() - startTime) / 1000);

            navigator.sendBeacon("/track/time", JSON.stringify({
                session_id: sessionId,
                duration: duration
            }));
        });

        // -----------------------------
        // LIKE BUTTON (FIXED)
        // -----------------------------
        const likeBtn = document.getElementById("likeBtn");

        if (likeBtn) {
            likeBtn.addEventListener("click", () => {

                fetch(`/track/like/${slug}`, {
                    method: "POST"
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

                fetch(`/track/share/${slug}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ platform: platform })
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