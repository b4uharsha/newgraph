import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import relativeLinks from 'astro-relative-links';
export default defineConfig({
  image: {
    service: { entrypoint: 'astro/assets/services/noop' },
  },
  integrations: [
    relativeLinks(),
    starlight({
      title: 'Graph OLAP Platform',
      description: 'HSBC Handover Documentation',
      lastUpdated: true,
      customCss: ['./src/styles/custom.css'],
      components: {
        // Injects bundled mermaid + ELK — see src/components/CustomHead.astro
        Head: './src/components/CustomHead.astro',
      },
      head: [
        // Mark the homepage for CSS targeting
        { tag: 'script', content: 'if (location.pathname === "/" || location.pathname === "") document.documentElement.setAttribute("data-home", "true");' },
      ],
      sidebar: [
        {
          label: 'Getting Started',
          collapsed: true,
          autogenerate: { directory: 'hsbc-deployment' },
        },
        {
          label: 'Operating the Platform',
          collapsed: true,
          autogenerate: { directory: 'operations' },
        },
        {
          label: 'System Architecture',
          collapsed: true,
          items: [
            { label: 'Architecture', collapsed: true, autogenerate: { directory: 'architecture' } },
            { label: 'API Specifications', collapsed: true, autogenerate: { directory: 'api' } },
            { label: 'Services', collapsed: true, autogenerate: { directory: 'component-designs' } },
          ],
        },
        {
          label: 'SDK & Tutorials',
          collapsed: true,
          autogenerate: { directory: 'sdk-manual' },
        },
        {
          label: 'Notebooks',
          collapsed: true,
          items: [
            { label: 'Tutorial', collapsed: true, autogenerate: { directory: 'notebooks/tutorial' } },
            { label: 'Reference', collapsed: true, autogenerate: { directory: 'notebooks/reference' } },
            { label: 'E2E', collapsed: true, autogenerate: { directory: 'notebooks/e2e' } },
            { label: 'UAT', collapsed: true, autogenerate: { directory: 'notebooks/uat' } },
          ],
        },
        {
          label: 'Security & Compliance',
          collapsed: true,
          items: [
            { label: 'Security', collapsed: true, autogenerate: { directory: 'security' } },
            { label: 'Governance', collapsed: true, autogenerate: { directory: 'governance' } },
            { label: 'Development Standards', collapsed: true, autogenerate: { directory: 'standards' } },
          ],
        },
        {
          label: 'Reference',
          collapsed: true,
          items: [
            { label: 'Developer Guide', collapsed: true, autogenerate: { directory: 'developer-guide' } },
            { label: 'Technical Reference', collapsed: true, autogenerate: { directory: 'reference' } },
          ],
        },
        {
          // Decision Records — ADR-149 Update §2 Tier-B.18 allow-list.
          // Populated by tools/repo-split/build-handover.sh::copy_adrs() which
          // copies 17 HSBC-scope ADRs (128-138, 140, 143, 144, 146-148) from
          // docs/process/adr/<category>/ into handover/decision-records/<category>/.
          // The broader ADR tree under docs/process/adr/ is intentionally
          // EXCLUDED from the handover — this is an allow-list, not a dump.
          label: 'Decision Records',
          collapsed: true,
          autogenerate: { directory: 'decision-records' },
        },
      ],
    }),
  ],
});
