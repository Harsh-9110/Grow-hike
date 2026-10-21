import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const base = process.env.BASE_URL || 'http://localhost:5173';
const screenshots = fileURLToPath(new URL('../docs/screenshots/', import.meta.url));
await mkdir(screenshots,{recursive:true});
await mkdir('artifacts',{recursive:true});
const browser = await chromium.launch({headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:'artifacts',size:{width:1440,height:1000}}});
const page = await context.newPage();
const errors = [];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)errors.push(`HTTP ${r.status()} on ${new URL(r.url()).pathname}`);});
async function nav(name,heading) {
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true}).click();
  await page.getByRole('heading',{name:heading,exact:true}).waitFor();
}
try {
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:/Explore the seeded demo/}).click();
  await page.getByRole('heading',{name:'Your holdings',exact:true}).waitFor();
  await page.screenshot({path:screenshots+'overview-dark.png',fullPage:true});
  await page.getByRole('button',{name:'Switch to light mode',exact:true}).click();
  await page.screenshot({path:screenshots+'overview-light.png',fullPage:true});
  await page.getByRole('button',{name:'Switch to dark mode',exact:true}).click();
  await nav('Markets','Markets');
  await page.getByText('Reliance Industries',{exact:true}).last().waitFor();
  await page.screenshot({path:screenshots+'markets.png',fullPage:true});
  await nav('Paper trading','Paper trading');
  const buy=page.getByRole('button',{name:'Buy RELIANCE.NS',exact:true});
  await buy.click();
  await page.getByText('Paper trade recorded in your immutable ledger.',{exact:true}).waitFor();
  await buy.click();
  await page.getByText('Your earlier order was already recorded. No duplicate trade was made.',{exact:true}).waitFor();
  await nav('Import portfolio','Import portfolio');
  await page.locator('input[type=file]').setInputFiles(fileURLToPath(new URL('../samples/portfolio.csv',import.meta.url)));
  await page.getByRole('button',{name:/Validate & preview/}).click();
  await page.getByText('Validation passed',{exact:true}).waitFor();
  await page.screenshot({path:screenshots+'import-preview.png',fullPage:true});
  await page.getByRole('button',{name:'Confirm import',exact:true}).click();
  await page.getByRole('heading',{name:'Your holdings',exact:true}).waitFor();
  await nav('AI lab','AI lab');
  await page.getByRole('button',{name:/Explore insights/}).click();
  await page.getByRole('heading',{name:'News, with a source',exact:true}).waitFor();
  await page.screenshot({path:screenshots+'ai-lab.png',fullPage:true});
  await nav('IPO & GMP','IPO & GMP');
  await page.getByRole('button',{name:/Calculate scenario/}).click();
  await page.getByText('₹115.00',{exact:true}).waitFor();
  await nav('System metrics','System metrics');
  await page.getByRole('heading',{name:'A look under the hood',exact:true}).waitFor();
  await page.screenshot({path:screenshots+'metrics.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await nav('Overview','Room to grow.');
  await page.getByRole('heading',{name:'Your holdings',exact:true}).waitFor();
  await page.screenshot({path:screenshots+'overview-mobile.png',fullPage:true});
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('Browser smoke passed: login, themes, markets, idempotent trade retry, import, AI fallback, IPO, metrics and mobile.');
} finally {
  const video=page.video();
  await context.close();
  if(video)await video.saveAs('artifacts/demo.webm');
  await browser.close();
}

const readmeUrl=new URL('../README.md',import.meta.url);
const readme=await readFile(readmeUrl,'utf8');
const media=['','![Dark portfolio overview](docs/screenshots/overview-dark.png)','',
  '![Light portfolio overview](docs/screenshots/overview-light.png)','',
  '![Import preview](docs/screenshots/import-preview.png)','',
  '![Mobile portfolio](docs/screenshots/overview-mobile.png)','',
  '[Recorded browser walkthrough](e2e/artifacts/demo.webm)',''].join('\n');
await writeFile(readmeUrl,readme.replace(/(<!-- BROWSER_MEDIA_START -->)[\s\S]*?(<!-- BROWSER_MEDIA_END -->)/,`$1${media}$2`));
