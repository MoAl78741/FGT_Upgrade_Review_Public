const {test,expect}=require('../../frontend/node_modules/@playwright/test');
const fs=require('node:fs'),path=require('node:path');
const pro=process.env.SUITE_EDITION==='private',password='test-only-correct-horse-battery';
const token=fs.readFileSync(path.join(process.env.SUITE_SANDBOX,'test-only'),'utf8');
const control={headers:{'X-Test-Control':token}};
test.beforeEach(async({page,request})=>{
 expect((await request.post('/__test/reset',{...control,data:{}})).ok()).toBeTruthy();
 page.__errors=[];page.on('pageerror',error=>page.__errors.push(error.message));page.on('response',r=>{if(r.status()>=500)page.__errors.push(r.status()+' '+r.url())});
 await page.route('**/*',route=>{const u=new URL(route.request().url());return ['127.0.0.1','localhost'].includes(u.hostname)||['data:','blob:'].includes(u.protocol)?route.continue():route.abort('blockedbyclient')});
});
test.afterEach(async({page})=>{expect(page.__errors).toEqual([])});
async function open(page,url='/'){
 await page.goto('/');
 if(pro){await page.getByLabel('Username',{exact:true}).fill('admin');await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.getByRole('button',{name:'Scrape documentation',exact:true})).toBeVisible();}
 await expect(page.getByTestId('build-info')).toContainText('test-suite');
 if(url!=='/')await page.goto(url);
}
async function seed(page){await open(page);const response=await page.request.post('/__test/seed',control);expect(response.ok(),await response.text()).toBeTruthy();await page.goto('/reports/fixture');await expect(page.getByRole('button',{name:'Download HTML',exact:true})).toBeVisible();}

test('@feature:navigation home links, build identity, theme and mobile overflow',async({page})=>{
 await open(page);await expect(page.getByTestId('build-info')).toContainText('test-suite');
 const toggle=page.getByRole('button',{name:/Switch to .* mode/});const label=await toggle.getAttribute('aria-label');await toggle.click();await page.reload();await expect(toggle).not.toHaveAttribute('aria-label',label);
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Reports',exact:true}).click();await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Home',exact:true}).click();await expect(page).toHaveURL(/\/$/);
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('@feature:release_selection dropdowns and valid/invalid scrape ranges',async({page})=>{
 await open(page);if(pro)await expect(page.getByRole('button',{name:'Scrape documentation',exact:true})).toHaveAttribute('aria-pressed','true');
 let options;
 if(pro){const from=page.getByRole('combobox',{name:'From',exact:true}),to=page.getByRole('combobox',{name:'To',exact:true});await expect(from.locator('option[value="7.6.6"]')).toBeAttached();options=await from.locator('option').evaluateAll(xs=>xs.map(x=>x.value));await from.selectOption('7.6.6');await to.selectOption('7.6.5');await expect(page.getByRole('button',{name:'Start Scrape',exact:true})).toBeDisabled();}
 if(pro)await page.getByRole('button',{name:'Upload PDFs',exact:true}).click();await page.getByText('Help me find PDFs for a version range',{exact:true}).click();if(pro){const from=page.getByRole('combobox',{name:'From',exact:true});await expect(from.locator('option[value="7.6.6"]')).toBeAttached();expect(await from.locator('option').evaluateAll(xs=>xs.map(x=>x.value))).toEqual(options);await from.selectOption('7.6.5');await page.getByRole('combobox',{name:'To',exact:true}).selectOption('7.6.6');}
 else{await expect(page.locator('#pdf-release-versions option[value="7.6.6"]')).toBeAttached();await page.getByRole('combobox',{name:'From version',exact:true}).fill('7.6.5');await page.getByRole('combobox',{name:'To version',exact:true}).fill('7.6.6');}
 await page.getByRole('button',{name:'Find PDF links',exact:true}).click();await expect(page.getByRole('link',{name:/7.6.6/}).first()).toHaveAttribute('href',/docs.fortinet.com/);
});
test('@feature:report_content mixed aliases preserve rows and source formatting',async({page})=>{
 await seed(page);await page.getByRole('button',{name:/Resolved Issues/}).click();await expect(page.getByText('Legacy resolved sentinel',{exact:true})).toBeVisible();await expect(page.getByText('Current resolved sentinel',{exact:true})).toBeVisible();
 const original=await(await page.request.get('/api/jobs/fixture')).json();expect(original.all_data['7.6.5']['resolved-issue']).toHaveLength(1);
 await page.getByRole('button',{name:/Known Issues/}).click();await expect(page.locator('strong').filter({hasText:'source sentinel'}).first()).toBeVisible();
});
test('@feature:archives missing originals retain archive and warn',async({page})=>{
 await seed(page);await page.goto('/');const event=page.waitForEvent('download');await page.getByRole('button',{name:'Download session archive',exact:true}).click();const download=await event;const file=await download.path();expect(fs.statSync(file).size).toBeGreaterThan(1000);await expect(page.getByText(/Archive downloaded with 1 warning/)).toBeVisible();
});
test('@feature:progress per-document pages, time, outcome and missing source',async({page})=>{
 await seed(page);await page.getByText('PDF documents · pages and processing times',{exact:true}).click();await expect(page.getByText('17 pages',{exact:false})).toBeVisible();await expect(page.getByLabel('Completed',{exact:true})).toBeVisible();await expect(page.getByText(/Original PDF unavailable/).first()).toBeVisible();
});
test('@feature:config_analysis configuration remains browser-only and clears',async({page})=>{
 await seed(page);const marker='PRIVATE_CONFIG_SENTINEL_'+Date.now();const requests=[],mutations=[];page.on('request',r=>{requests.push(r.url()+' '+(r.postData()||''));if(r.method()!=='GET')mutations.push(r.method()+' '+r.url())});
 await page.getByLabel('Choose plaintext FortiOS backup (10 MiB maximum)').setInputFiles({name:marker+'.conf',mimeType:'text/plain',buffer:Buffer.from('config router bgp\n set as 64512\nend\nconfig system global\n set hostname "'+marker+'"\nend')});
 await expect(page.getByRole('combobox',{name:'BGP state',exact:true})).toHaveValue('configured');expect(requests.join(' ')).not.toContain(marker);expect(mutations).toEqual([]);expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(marker);
 await page.getByRole('button',{name:'Clear local analysis',exact:true}).click();await expect(page.getByRole('combobox',{name:'BGP state',exact:true})).toHaveCount(0);
});
test('@feature:authentication bootstrap password blocks data until changed',async({page,request})=>{
 test.skip(!pro,'Pro named-account bootstrap; Public operator covered separately.');await request.post('/__test/reset',{...control,data:{bootstrap:true}});await page.goto('/');await page.getByLabel('Username',{exact:true}).fill('admin');await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.getByLabel('New password',{exact:true})).toBeVisible();expect((await page.request.get('/api/jobs')).status()).toBe(403);await page.getByLabel('New password',{exact:true}).fill(password+'-changed');await page.getByLabel('Confirm new password',{exact:true}).fill(password+'-changed');await page.getByRole('button',{name:'Change password and continue',exact:true}).click();await expect(page.getByRole('button',{name:'Scrape documentation',exact:true})).toBeVisible();expect((await page.request.get('/api/jobs')).status()).toBe(200);
});
test('@feature:feature_gates disabled Pro modules disappear and deny direct API access',async({page,request})=>{
 test.skip(!pro,'Public has no optional Pro module switches.');await request.post('/__test/reset',{...control,data:{features:false}});await open(page);await expect(page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Upgrade reviews'})).toHaveCount(0);expect((await page.request.get('/api/reviews')).status()).toBe(403);expect((await page.request.get('/api/jobs')).status()).toBe(200);
});
const modules=pro?[['backups','Backup & restore'],['certificates','Certificates'],['event_logs','Event logs'],['processing_settings','Processing'],['product_packs','Packs'],['workspaces','Domains'],['team_accounts','Accounts'],['custom_roles','Access profiles'],['support','Support'],['syslog','Syslog'],['email','Email & schedules']]:[['backups','Backup & restore'],['certificates','Certificates'],['event_logs','Event logs']];
test(modules.map(([feature])=>'@feature:'+feature).join(' ')+' administration panels render without server failures',async({page})=>{
 test.setTimeout(90000);
 await open(page,'/administration');if(!pro){await page.getByLabel('Operator username').fill('operator');await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();}
 for(const [,label] of modules)await test.step(label,async()=>{const endpoint={'Certificates':'/api/administration/certificates','Event logs':'/api/administration/logs','Processing':'/api/settings/processing','Packs':'/api/administration/packs','Access profiles':'/api/administration/profiles','Syslog':'/api/administration/syslog','Email & schedules':'/api/administration/mail'}[label];const loaded=endpoint?page.waitForResponse(r=>new URL(r.url()).pathname===endpoint&&r.request().method()==='GET'):null;const button=page.getByRole('navigation',{name:'Administration sections'}).getByRole('button',{name:label,exact:true});await button.click();await expect(button).toHaveAttribute('aria-current','page');if(loaded)expect((await loaded).ok()).toBeTruthy();await expect(page.getByRole('alert')).toHaveCount(0);});
});
test('@feature:api_documentation Swagger is local, usable and lists export operations',async({page})=>{
 await open(page,'/api/docs');await expect(page.locator('.swagger-ui')).toBeVisible();await expect(page.getByText('/api/jobs/{job_id}/export',{exact:true}).first()).toBeVisible();
});

test('@feature:reviews saved decisions and checklist survive reload without changing source',async({page})=>{
 await seed(page);const original=await(await page.request.get('/api/jobs/fixture')).json();await page.goto('/reviews');await page.getByLabel('Review name',{exact:true}).fill('Synthetic upgrade');await page.getByRole('button',{name:'Create review',exact:true}).click();await expect(page).toHaveURL(/\/reviews\/[^/]+$/);
 await page.getByRole('combobox',{name:'Source report',exact:true}).selectOption('fixture');await page.getByRole('button',{name:'Add report',exact:true}).click();await expect(page.getByRole('combobox',{name:'Decision',exact:true}).first()).toBeVisible();
 await page.getByRole('combobox',{name:'Decision',exact:true}).first().selectOption('needs_testing');await page.getByLabel('Reviewer note',{exact:true}).first().fill('Exercise BGP failover in the lab');const saved=page.waitForResponse(r=>r.url().includes('/decisions/')&&r.request().method()==='PUT');await page.getByRole('button',{name:'Save decision',exact:true}).first().click();expect((await saved).ok()).toBeTruthy();await page.reload();await expect(page.getByRole('combobox',{name:'Decision',exact:true}).first()).toHaveValue('needs_testing');await expect(page.getByLabel('Reviewer note',{exact:true}).first()).toHaveValue('Exercise BGP failover in the lab');
 await page.getByText('Testing and rollback checklist',{exact:true}).click();await page.getByLabel('Checklist action',{exact:true}).fill('Verify rollback backup');await page.getByRole('button',{name:'Add action',exact:true}).click();await page.getByLabel('Completed: Verify rollback backup',{exact:true}).check();const checklist=page.waitForResponse(r=>r.url().endsWith('/checklist')&&r.request().method()==='PUT');await page.getByRole('button',{name:'Save checklist',exact:true}).click();expect((await checklist).ok()).toBeTruthy();await page.reload();await page.getByText('Testing and rollback checklist',{exact:true}).click();await expect(page.getByLabel('Completed: Verify rollback backup',{exact:true})).toBeChecked();
 expect((await(await page.request.get('/api/jobs/fixture')).json()).all_data).toEqual(original.all_data);
 const dl=page.waitForEvent('download');await page.getByRole('button',{name:'Download review package',exact:true}).click();const html=fs.readFileSync(await(await dl).path(),'utf8');expect(html).toContain('Exercise BGP failover in the lab');expect(html).toContain('Verify rollback backup');
});
test('@feature:processing_settings server limits save, survive reload and reset',async({page})=>{
 test.skip(!pro,'Public users cannot edit installation limits.');await open(page,'/administration');await page.getByRole('navigation',{name:'Administration sections'}).getByRole('button',{name:'Processing',exact:true}).click();const initial=await(await page.request.get('/api/settings/processing')).json();const minutes=initial.values.timeout_minutes===2?3:2;
 await page.getByLabel('Default PDF timeout (minutes)',{exact:false}).fill(String(minutes));await page.getByRole('button',{name:'Save installation settings',exact:true}).click();await expect(page.getByText('Installation settings saved. Applies to new uploads and retries.',{exact:true})).toBeVisible();await page.reload();await page.getByRole('navigation',{name:'Administration sections'}).getByRole('button',{name:'Processing',exact:true}).click();await expect(page.getByLabel('Default PDF timeout (minutes)',{exact:false})).toHaveValue(String(minutes));
 const reset=page.waitForResponse(r=>r.url().endsWith('/settings/processing')&&r.request().method()==='DELETE');await page.getByRole('button',{name:'Restore deployment defaults',exact:true}).click();expect((await reset).ok()).toBeTruthy();expect((await(await page.request.get('/api/settings/processing')).json()).values).toEqual(initial.defaults);
});
test('@feature:security public browser sessions cannot read, export or delete each other reports',async({page,browser,baseURL})=>{
 test.skip(pro,'Pro workspace isolation is exercised by API role/membership tests.');await seed(page);const other=await browser.newContext({baseURL,ignoreHTTPSErrors:true,extraHTTPHeaders:{Origin:baseURL}});
 try{expect((await other.request.get('/api/capabilities')).ok()).toBeTruthy();expect((await(await other.request.get('/api/jobs')).json()).length).toBe(0);for(const endpoint of ['/api/jobs/fixture','/api/jobs/fixture/export?format=json'])expect((await other.request.get(endpoint)).status()).toBe(404);expect((await other.request.delete('/api/jobs/fixture')).status()).toBe(404);expect((await page.request.get('/api/jobs/fixture')).status()).toBe(200);}finally{await other.close();}
});

test('@feature:pdf_import real multipart upload can cancel and retry without losing the original',async({page})=>{
 await open(page);if(pro)await page.getByRole('button',{name:'Upload PDFs',exact:true}).click();await page.locator('input[type=file]').first().setInputFiles({name:'fortios-v7.6.6-synthetic.pdf',mimeType:'application/pdf',buffer:fs.readFileSync(path.join(process.env.SUITE_SANDBOX,'synthetic.pdf'))});
 const upload=page.waitForResponse(r=>r.url().endsWith('/jobs/upload')&&r.request().method()==='POST');await page.getByRole('button',{name:'Process PDFs',exact:true}).click();const result=await upload;expect(result.ok(),await result.text()).toBeTruthy();const job=await result.json();
 await page.getByRole('button',{name:'Cancel',exact:true}).click();await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible();expect((await(await page.request.get('/api/jobs/'+job.id)).json()).status).toBe('cancelled');await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(page.getByRole('button',{name:'Cancel',exact:true})).toBeVisible();const retried=await(await page.request.get('/api/jobs/'+job.id)).json();expect(retried.status).toBe('pending');expect(retried.file_outcomes).toHaveLength(1);
});
test('@feature:consolidation duplicates merge only when checked and retain both builds',async({page})=>{
 await seed(page);const original=await(await page.request.get('/api/jobs/fixture')).json();await page.getByRole('button',{name:/Known Issues/}).click();await expect(page.getByRole('cell',{name:'123456',exact:true})).toHaveCount(2);await page.getByRole('checkbox',{name:'Consolidate duplicates',exact:true}).check();await expect(page.getByRole('cell',{name:'123456',exact:true})).toHaveCount(1);const row=page.getByRole('row').filter({has:page.getByRole('cell',{name:'123456',exact:true})});await expect(row).toContainText('7.6.5');await expect(row).toContainText('7.6.6');await page.getByRole('checkbox',{name:'Consolidate duplicates',exact:true}).uncheck();await expect(page.getByRole('cell',{name:'123456',exact:true})).toHaveCount(2);expect((await(await page.request.get('/api/jobs/fixture')).json()).all_data).toEqual(original.all_data);
});
test('@feature:exports standalone HTML preserves visible source wording and formatting',async({page})=>{
 await seed(page);await page.getByRole('button',{name:'Download HTML',exact:true}).click();const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download',exact:true}).click();const html=fs.readFileSync(await(await download).path(),'utf8');expect(html).toContain('Legacy resolved sentinel');expect(html).toContain('Current resolved sentinel');expect(html).toContain('<strong>source sentinel</strong>');expect(html).toContain('<strong>chapter</strong>');await page.route('**/__export',route=>route.fulfill({status:200,contentType:'text/html',body:html}));await page.goto('/__export');await page.getByRole('button',{name:/Known Issues/}).click();await expect(page.locator('strong').filter({hasText:'source sentinel'}).first()).toBeVisible();expect(await page.locator('script[src^="http"],img[src^="http"],link[href^="http"]').count()).toBe(0);
});
