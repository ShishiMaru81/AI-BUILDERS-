import type {Metadata} from 'next';
import './globals.css';
import './ui-motion.css';
export const metadata:Metadata={title:'ZYNTRIX · AgroSphere AI',description:'One connected workspace for healthier crops and informed farm decisions.'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en" suppressHydrationWarning><body>{children}</body></html>}
