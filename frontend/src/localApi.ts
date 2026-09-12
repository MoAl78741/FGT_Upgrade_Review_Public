/** Pure local interface. These functions never make requests or persist inputs. */
export {analyzeConfig, relevance, emptyProfile, FEATURES, RULE_VERSION} from './config/analyze';
export {reportView, reportHtml, reportDelimited} from './utils/reportApi';
export {compareFeatures} from './utils/featureComparison';
export {pdfReleaseRange, pdfCatalog} from './utils/pdfReleaseRange';
export {reviewPackageHtml} from './utils/reviewExport';
export {generateHtml, getAvailableSections} from './utils/htmlExport';
