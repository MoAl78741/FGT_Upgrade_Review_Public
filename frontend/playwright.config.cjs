const {defineConfig}=require('@playwright/test');
const path=require('node:path');
const base=`https://127.0.0.1:${process.env.SUITE_PORT}`;
if(!process.env.SUITE_SANDBOX||!process.env.SUITE_RESULTS||!process.env.SUITE_PORT)throw Error('Run through scripts/check.py; arbitrary live servers are not supported.');
const output=process.env.SUITE_RESULTS;
module.exports=defineConfig({testDir:'../tests/browser',timeout:60000,expect:{timeout:10000},workers:1,fullyParallel:false,forbidOnly:!!process.env.CI,retries:0,
 outputDir:path.join(output,'browser-artifacts'),reporter:[['list'],['json',{outputFile:path.join(output,'browser.json')}],['junit',{outputFile:path.join(output,'browser.xml')}],['html',{outputFolder:path.join(output,'browser-report'),open:'never'}]],
 use:{actionTimeout:15000,navigationTimeout:30000,baseURL:base,ignoreHTTPSErrors:true,extraHTTPHeaders:{Origin:base},trace:'retain-on-failure',screenshot:'only-on-failure',launchOptions:{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}},
 webServer:{command:`"${process.env.PYTHON_BINARY}" ../tests/browser_server.py`,url:base+'/api/health',ignoreHTTPSErrors:true,reuseExistingServer:false,timeout:60000}});
