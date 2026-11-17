# Premier Casino website preview

Read-only copy built from the published Webflow pages. It includes navigation, location pages, Careers layout, animations, documents and their local images and fonts. Google Maps and optional Inter font loading still use Google. Preview pages request no indexing. The contact form, application form and Lucky integration have been replaced with links to the official site. Example jobs represent the archived layout.

## Run and rebuild

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory docs
python3 check.py
```

To recreate the published files, point the builder at the authorized `production-webflow` snapshot and use an empty output folder, then review the generated changes. The default output is `docs/`. The full Webflow migration archive and CMS exports belong in the private workspace.

```sh
python3 build.py /path/to/production-webflow --output /tmp/premier-build
python3 check.py /tmp/premier-build
```

## Hosting

| Target | Configuration |
| --- | --- |
| GitHub Pages | Publish this repository's `main` branch from `/docs`. The preview uses a project path and includes `.nojekyll`. |
| Vercel | Import this repository as a separate project. `vercel.json` serves `docs/` and supports extensionless routes. Use a Vercel preview deployment to check changes. |
| DigitalOcean | Serve the contents of `docs/` on the Droplet with Nginx. `deploy/nginx.conf` is an example for a service behind a TLS proxy. Set the production hostname at the proxy when the site is ready. |

Keep a staging URL for reviewing a specific revision. Promote the tested commit to production through a separate branch or release. Before switching the live domain, reconnect the CRM, implement the contact endpoint, connect the new CMS and analytics, verify the old URLs and sitemap, and test a synthetic application with an upload. Removing the preview notice by itself does not enable live services.
