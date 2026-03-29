import fs from 'node:fs/promises';
import path from 'node:path';

const astroRoot = process.cwd();
const localRepoDocs = path.resolve(astroRoot, '..', 'src', 'docs');
const containerDocs = '/workspace-docs';
const sourceRoot = process.env.DOCS_SOURCE_DIR || containerDocs;
const targetRoot = path.join(astroRoot, 'src', 'content', 'docs', 'generated');

async function pathExists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function recreateDir(dir) {
  await fs.rm(dir, { recursive: true, force: true });
  await ensureDir(dir);
}

function prettifyTitle(segment) {
  return segment
    .replace(/^\d+-/, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function injectFrontmatter(title, body) {
  if (body.startsWith('---\n')) return body;
  return `---\ntitle: ${title}\n---\n\n${body}`;
}

async function copyReadmes(currentDir, relativeDir = '') {
  const entries = await fs.readdir(currentDir, { withFileTypes: true });

  for (const entry of entries) {
    const sourcePath = path.join(currentDir, entry.name);
    const nextRelativeDir = path.join(relativeDir, entry.name);

    if (entry.isDirectory()) {
      await copyReadmes(sourcePath, nextRelativeDir);
      continue;
    }

    if (entry.name !== 'README.md') continue;

    const sourceFolder = path.basename(path.dirname(sourcePath));
    const targetDir = path.join(targetRoot, path.dirname(relativeDir));
    const targetFile = path.join(targetDir, `${sourceFolder}.md`);
    const markdown = await fs.readFile(sourcePath, 'utf8');
    const title = prettifyTitle(sourceFolder);

    await ensureDir(targetDir);
    await fs.writeFile(targetFile, injectFrontmatter(title, markdown), 'utf8');
  }
}

async function main() {
  const resolvedSource = (await pathExists(sourceRoot)) ? sourceRoot : localRepoDocs;
  await recreateDir(targetRoot);
  await copyReadmes(resolvedSource);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
