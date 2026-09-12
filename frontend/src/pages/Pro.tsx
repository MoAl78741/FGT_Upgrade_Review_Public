import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {api} from '../api';
const benefits = [
 ['Keep your work','Reports, source PDFs and reviews stay on your installation until you delete them.'],
 ['Work as a team','Named accounts, customer domains and custom permission profiles keep access organized.'],
 ['Run on your own infrastructure','Docker deployment and offline PDF processing after installation. Configuration analysis stays in your browser.'],
 ['Manage the installation','Encrypted backup and restore, HTTPS certificate management, diagnostics and processing settings.'],
 ['Stay informed','Local logs, syslog, job-failure and completed-review email notifications, plus scheduled summary emails.'],
 ['Choose your sources','Import PDFs or enable documentation scraping through trusted operator configuration.'],
];
export default function Pro(){const {data}=useQuery({queryKey:['capabilities'],queryFn:api.capabilities});return <div className="max-w-5xl mx-auto p-6 py-12 space-y-8"><div className="space-y-4"><p className="text-brand-500 font-semibold">UPGRADE REVIEW PRO</p><h1 className="text-4xl font-semibold text-white">Keep your reviews. Bring your team.</h1><p className="text-lg text-gray-300">Move from temporary public sessions to a persistent installation you control.</p></div><div className="grid sm:grid-cols-2 gap-4">{benefits.map(([title,body])=><section key={title} className="rounded-xl border border-navy-600 bg-navy-800 p-6"><h2 className="text-lg font-semibold text-white">{title}</h2><p className="text-gray-300 mt-2">{body}</p></section>)}</div><section className="rounded-xl bg-navy-800 border border-navy-600 p-6 space-y-4"><h2 className="text-xl font-semibold text-white">Ready for Pro?</h2>{data?.pro_upgrade_url?<a href={data.pro_upgrade_url} rel="noopener noreferrer" target="_blank" className="inline-block rounded-lg bg-brand-500 text-white px-5 py-3">Get Pro</a>:<p className="text-gray-300">A signup or contact destination has not been configured for this installation yet.</p>}<p className="text-sm text-gray-400">Pro is a separate deployment. This button does not transfer your public session or documents. Download your work before its expiry.</p><Link to="/" className="text-brand-500 underline">Continue with Public</Link></section></div>}
