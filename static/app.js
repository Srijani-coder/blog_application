function getDeviceId() {
    let id = localStorage.getItem("device_id");

    if (!id) {
        id = "dev-" + Math.random().toString(36).substring(2) + Date.now();
        localStorage.setItem("device_id", id);
    }

    return id;
}

function formatSeconds(seconds) {
    seconds = Number(seconds || 0);
    if (seconds < 60) return `${Math.round(seconds)} sec`;
    const minutes = Math.floor(seconds / 60);
    const remaining = Math.round(seconds % 60);
    return remaining ? `${minutes} min ${remaining} sec` : `${minutes} min`;
}

document.addEventListener("DOMContentLoaded", () => {

    // =============================
    // TRENDING TOGGLE
    // =============================
    const btn = document.getElementById("toggleTrending");
    const grid = document.getElementById("postGrid");

    if (btn && grid) {
        btn.addEventListener("click", () => {
            grid.classList.toggle("trending");
            document.body.style.filter = grid.classList.contains("trending") ? "saturate(1.1)" : "none";
        });
    }

    // =============================
    // POST PAGE ANALYTICS
    // =============================
    const postContainer = document.querySelector(".comments[data-slug]");

    if (postContainer) {
        const slug = postContainer.dataset.slug;
        let sessionId = null;
        const startTime = Date.now();
        let maxSentDuration = 0;

        function updateStatText(data) {
            const likeCount = document.getElementById("likeCount");
            const inlineLikeCount = document.getElementById("inlineLikeCount");
            const shareCount = document.getElementById("shareCount");
            const viewCount = document.getElementById("viewCount");
            const avgTimeCount = document.getElementById("avgTimeCount");

            if (likeCount && data.likes !== undefined) likeCount.innerText = data.likes;
            if (inlineLikeCount && data.likes !== undefined) inlineLikeCount.innerText = data.likes;
            if (shareCount && data.shares !== undefined) shareCount.innerText = data.shares;
            if (viewCount && data.views !== undefined) viewCount.innerText = data.views;
            if (avgTimeCount && data.avg_time_seconds !== undefined) {
                avgTimeCount.innerText = formatSeconds(data.avg_time_seconds);
            }
        }

        fetch(`/track/view/${slug}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: getDeviceId() })
        })
            .then(res => res.json())
            .then(data => {
                sessionId = data.session_id;
                updateStatText(data);
                return fetch(`/track/stats/${slug}`);
            })
            .then(res => res ? res.json() : null)
            .then(data => { if (data) updateStatText(data); })
            .catch(err => console.error("View tracking error:", err));

        function sendTime(useBeacon = false) {
            if (!sessionId) return;

            const duration = Math.floor((Date.now() - startTime) / 1000);
            if (duration <= maxSentDuration) return;
            maxSentDuration = duration;

            const payload = JSON.stringify({
                session_id: sessionId,
                duration: duration
            });

            if (useBeacon && navigator.sendBeacon) {
                const blob = new Blob([payload], { type: "application/json" });
                navigator.sendBeacon("/track/time", blob);
                return;
            }

            fetch("/track/time", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: payload,
                keepalive: true
            }).catch(err => console.error("Time tracking error:", err));
        }

        setInterval(() => sendTime(false), 15000);
        window.addEventListener("beforeunload", () => sendTime(true));
        window.addEventListener("pagehide", () => sendTime(true));
        window.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") sendTime(true);
        });

        const likeBtn = document.getElementById("likeBtn");
        if (likeBtn) {
            likeBtn.addEventListener("click", () => {
                fetch(`/track/like/${slug}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ device_id: getDeviceId() })
                })
                    .then(res => res.json())
                    .then(data => {
                        updateStatText(data);
                        if (!data.liked) likeBtn.innerText = `👍 Already liked (${data.likes})`;
                    })
                    .catch(err => console.error("Like error:", err));
            });
        }

        document.querySelectorAll(".share-btn").forEach(button => {
            button.addEventListener("click", () => {
                const platform = button.dataset.platform;
                const url = encodeURIComponent(window.location.href);

                if (platform === "twitter") window.open(`https://twitter.com/intent/tweet?url=${url}`);
                if (platform === "linkedin") window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${url}`);

                fetch(`/track/share/${slug}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ platform: platform, device_id: getDeviceId() })
                })
                    .then(res => res.json())
                    .then(data => updateStatText(data))
                    .catch(err => console.error("Share error:", err));
            });
        });
    }
});

// Admin DOCX import helper: reminds the admin to add image alt text before publishing.
document.addEventListener('DOMContentLoaded', function () {
  const docInput = document.getElementById('docfileInput');
  const altBox = document.getElementById('docxAltTextBox');
  if (!docInput || !altBox) return;

  docInput.addEventListener('change', function () {
    const file = docInput.files && docInput.files[0];
    if (!file) return;
    if (file.name.toLowerCase().endsWith('.docx')) {
      altBox.focus();
      if (!altBox.value.trim()) {
        altBox.placeholder = 'DOCX selected. Enter one alt text per line for each image in the Word document.\nExample:\nCustomer analytics dashboard screenshot\nBusiness owner profile image\nEvent photo from client office';
      }
    }
  });
});
