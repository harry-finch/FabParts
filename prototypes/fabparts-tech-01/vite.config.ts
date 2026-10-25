import { cpSync } from 'node:fs';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
export default defineConfig({
  plugins: [svelte(), {name:'local-pdf-assets', closeBundle(){
cpSync('node_modules/pdfjs-dist/LICENSE','dist/PDFJS-LICENSE.txt');
cpSync('../../third_party/licenses','dist/licenses',{recursive:true});
for(const dir of ['cmaps','standard_fonts']) cpSync(`node_modules/pdfjs-dist/${dir}`,`dist/pdfjs/${dir}`,{recursive:true});
}}],
  publicDir: '../fabparts-ux/public',
  resolve: { dedupe: ['svelte', '@lucide/svelte'] },
  build: { target: 'es2022' },
});
