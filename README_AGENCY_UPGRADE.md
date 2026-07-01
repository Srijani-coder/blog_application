# Creative Tech Partner by Srijani - Agency Portfolio Upgrade

This version converts the blog into a website developer agency portfolio and advertisement website while keeping the existing blog/CMS/admin structure.

## New public pages
- `/` agency landing page
- `/services` services page
- `/portfolio` portfolio and proof page
- `/contact` WhatsApp contact page
- `/posts` existing blog archive

## Added positioning
- AI based website development and site development
- Frontend and backend development
- CMS admin portal
- SEO strategy and technical SEO
- AI chatbot development
- Analytics dashboards and automation

## WhatsApp contact
Set your number in environment variables:

```env
WHATSAPP_NUMBER=918101260237
CONTACT_EMAIL=your-email@example.com
```

The button uses `https://wa.me/` and opens a pre-filled lead message.

## Run locally
```bash
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Then open the local Flask URL shown in your terminal.

## Important security note
The original `.env` file contained live secrets, so it was removed from this zip and replaced with `.env.example`.
