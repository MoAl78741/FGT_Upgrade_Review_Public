import {useEffect} from 'react';
import {Link, useLocation} from 'react-router-dom';
export default function Breadcrumbs() {
  const {pathname} = useLocation();
  useEffect(() => {window.scrollTo(0, 0);}, [pathname]);
  if (pathname === '/') return null;
  const review = pathname.startsWith('/reviews/');
  const current = review ? 'Review details' : pathname.startsWith('/reports/') ? 'Source report' : pathname === '/reviews' ? 'Upgrade reviews' : pathname === '/account' ? 'Account & access' : pathname === '/installation' ? 'Setup & support' : 'Page';
  return <nav aria-label="Breadcrumb" className="max-w-screen-xl mx-auto px-6 pt-5 text-sm text-gray-300">
    <ol className="flex flex-wrap items-center gap-2">
      <li><Link className="text-brand-500 underline" to="/">Home</Link></li>
      {review && <><li aria-hidden="true">/</li><li><Link className="text-brand-500 underline" to="/reviews">Upgrade reviews</Link></li></>}
      <li aria-hidden="true">/</li><li aria-current="page">{current}</li>
    </ol>
  </nav>;
}
