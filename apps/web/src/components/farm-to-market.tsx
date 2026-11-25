'use client';

import {useEffect, useRef, useState} from 'react';
import Link from 'next/link';
import {ArrowRight} from 'lucide-react';
import styles from './farm-to-market.module.css';

export function FarmToMarket({locale, crop}: {locale:'en'|'bn'; crop?:string}) {
  const bangla=locale==='bn';
  const cargo=crop==='potato'?styles.potato:crop==='tomato'?styles.tomato:styles.mixed;
  const scene=useRef<HTMLDivElement>(null);
  const [driving,setDriving]=useState(false);
  useEffect(()=>{
    const element=scene.current;
    if (!element) return;
    const observer=new IntersectionObserver(([entry])=>{
      if (!entry?.isIntersecting) return;
      setDriving(true);
      observer.disconnect();
    },{threshold:0.35});
    observer.observe(element);
    return ()=>observer.disconnect();
  },[]);
  return <section className={styles.card}>
    <div className={styles.content}>
      <h2>{bangla?'খামার থেকে বাজারে':'From farm to market'}</h2>
      <Link className={styles.link} href={`/${locale}/market`}>
        {bangla?'বিক্রির দাম তুলনা করুন':'Compare selling prices'} <ArrowRight size={16}/>
      </Link>
    </div>
    <div ref={scene} className={styles.scene} aria-hidden="true" data-testid="farm-route-scene">
      <span className={styles.sun}/>
      <span className={styles.hills}/>
      <span className={styles.field}/>
      <span className={styles.barn}><i/></span>
      <span className={styles.stall}><i/><b/></span>
      <span className={styles.road}/>
      <span className={driving?`${styles.truck} ${styles.driving}`:styles.truck} data-testid="farm-route-truck">
        <span className={`${styles.crate} ${cargo}`}/>
        <span className={`${styles.crate} ${cargo}`}/>
        <span className={styles.bed}/>
        <span className={styles.cab}/>
        <span className={styles.wheel}/>
        <span className={styles.wheel}/>
      </span>
    </div>
  </section>;
}
