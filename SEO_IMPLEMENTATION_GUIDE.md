# SEO implementation added

This version adds production SEO best practices to the Flask blog:

1. Dynamic `/sitemap.xml` with post URLs and image sitemap tags.
2. `/robots.txt` pointing to sitemap and blocking admin/unsubscribe URLs.
3. `/feed.xml` RSS feed for latest posts.
4. `/llms.txt` for AI-search discovery.
5. Canonical URL handling without query strings.
6. Optional `SITE_URL` environment variable for stable production canonical URLs.
7. Article JSON-LD schema on each post.
8. Website JSON-LD schema globally.
9. Breadcrumb JSON-LD on post pages.
10. Open Graph and Twitter Card metadata.
11. Image alt text, lazy loading, and fetchpriority for main image.
12. Reading-time estimates.
13. X-Robots-Tag noindex headers for admin and unsubscribe pages.
14. Security headers: X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
15. Accessibility skip link and improved semantic article markup.

## Required Render environment variable

Set this in Render environment variables:

```bash
SITE_URL=https://yourdomain.com
```

Until you buy a custom domain, use:

```bash
SITE_URL=https://statdash.onrender.com
```

After deploying, submit this sitemap in Google Search Console:

```text
https://yourdomain.com/sitemap.xml
```

Also test:

```text
https://yourdomain.com/robots.txt
https://yourdomain.com/feed.xml
https://yourdomain.com/llms.txt
```

## Important

Code helps Google crawl and understand the website. Ranking #1 still needs niche keyword targeting, backlinks, original datasets, internal links, and consistent publishing.
