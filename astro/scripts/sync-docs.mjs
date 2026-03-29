import fs from 'node:fs/promises';
import path from 'node:path';

const astroRoot = process.cwd();
const localRepoDocs = path.resolve(astroRoot, '..', 'src', 'docs');
const containerDocs = '/workspace-docs';
const sourceRoot = process.env.DOCS_SOURCE_DIR || containerDocs;
const targetRoot = path.join(astroRoot, 'src', 'pages');

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
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function titleFromRelativePath(relativePath) {
  const parsed = path.parse(relativePath);
  if (parsed.name === 'index' && !parsed.dir) {
    return 'PW-Airport Documentation';
  }

  const basename = parsed.name === 'index'
    ? path.basename(parsed.dir || 'docs')
    : parsed.name;

  return prettifyTitle(basename);
}

function layoutPathFor(relativePath) {
  const segments = relativePath.split(path.sep).filter(Boolean);
  const upLevels = '../'.repeat(segments.length);
  return `${upLevels}layouts/DocsLayout.astro`;
}

function ensurePageFrontmatter(relativePath, body) {
  const title = titleFromRelativePath(relativePath);
  const layout = layoutPathFor(relativePath);

  if (!body.startsWith('---\n')) {
    return `---\ntitle: ${title}\nlayout: ${layout}\n---\n\n${body}`;
  }

  if (body.includes('\nlayout:')) {
    return body;
  }

  const end = body.indexOf('\n---\n', 4);
  if (end === -1) {
    return body;
  }

  const frontmatter = body.slice(0, end);
  const content = body.slice(end);
  return `${frontmatter}\nlayout: ${layout}${content}`;
}

async function copyDocs(currentDir, relativeDir = '') {
  const entries = await fs.readdir(currentDir, { withFileTypes: true });

  for (const entry of entries) {
    const sourcePath = path.join(currentDir, entry.name);
    const nextRelativeDir = path.join(relativeDir, entry.name);

    if (entry.isDirectory()) {
      await copyDocs(sourcePath, nextRelativeDir);
      continue;
    }

    if (!['.md', '.mdx'].includes(path.extname(entry.name))) continue;

    const targetDir = path.join(targetRoot, path.dirname(nextRelativeDir));
    const targetFile = path.join(targetRoot, nextRelativeDir);
    const source = await fs.readFile(sourcePath, 'utf8');
    const content = ensurePageFrontmatter(nextRelativeDir, source);

    await ensureDir(targetDir);
    await fs.writeFile(targetFile, content, 'utf8');
  }
}

async function main() {
  const resolvedSource = (await pathExists(sourceRoot)) ? sourceRoot : localRepoDocs;
  await recreateDir(targetRoot);
  await copyDocs(resolvedSource);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
