import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'http://localhost:8001',
  base: '/docs',
  integrations: [
    starlight({
      title: 'PW-Airport Docs',
      description: 'Project architecture, workflows, Docker setup, and operational notes.',
      sidebar: [
        {
          label: 'Documentation',
          autogenerate: { directory: 'generated' }
        }
      ]
    })
  ]
});
