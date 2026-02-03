
document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("toggleTrending");
    const grid = document.getElementById("postGrid");
    if (!btn || !grid) return;

    btn.addEventListener("click", () => {
        grid.classList.toggle("trending");
        if (grid.classList.contains("trending")) {
            document.body.style.filter = "saturate(1.1)";
        } else {
            document.body.style.filter = "none";
        }
    });
});
