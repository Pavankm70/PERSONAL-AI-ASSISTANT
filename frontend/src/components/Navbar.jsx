import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { BrandLogo } from './BrandLogo';
import { Menu, X, ArrowRight } from 'lucide-react';

export const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleNavClick = (path) => {
    setMobileMenuOpen(false);
    if (path.startsWith('/#')) {
      if (location.pathname !== '/') {
        navigate('/');
        setTimeout(() => {
          const elem = document.getElementById(path.replace('/#', ''));
          if (elem) elem.scrollIntoView({ behavior: 'smooth' });
        }, 150);
      } else {
        const elem = document.getElementById(path.replace('/#', ''));
        if (elem) elem.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
      navigate(path);
    }
  };

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-[#08090B]/90 backdrop-blur-md border-b border-white/10 shadow-lg shadow-black/50'
          : 'bg-[#08090B]/40 backdrop-blur-sm border-b border-white/5'
      }`}
    >
      <div className="container mx-auto px-6 h-18 flex items-center justify-between">
        {/* Brand */}
        <div
          onClick={() => handleNavClick('/')}
          className="cursor-pointer"
        >
          <BrandLogo size="md" />
        </div>

        {/* Center Nav Links - Desktop */}
        <nav className="hidden md:flex items-center gap-8">
          {[
            { name: 'Platform', href: '/#platform' },
            { name: 'Capabilities', href: '/#capabilities' },
            { name: 'How It Works', href: '/#how-it-works' },
            { name: 'Security', href: '/#security' },
            { name: 'FAQ', href: '/#faq' }
          ].map((item) => (
            <button
              key={item.name}
              onClick={() => handleNavClick(item.href)}
              className="text-[#A1A4AA] hover:text-white text-sm font-medium transition-colors tracking-wide bg-transparent border-0 cursor-pointer"
            >
              {item.name}
            </button>
          ))}
        </nav>

        {/* Right Action Buttons */}
        <div className="hidden md:flex items-center gap-4">
          <button
            onClick={() => handleNavClick('/auth')}
            className="btn-ghost text-sm font-medium"
          >
            Sign In
          </button>

          <button
            onClick={() => handleNavClick('/app')}
            className="btn-bronze text-sm"
          >
            <span>Launch App</span>
            <ArrowRight size={14} />
          </button>
        </div>

        {/* Mobile menu trigger */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden flex items-center justify-center p-2 rounded-md bg-[#181B20] border border-white/10 text-[#F5F3EE]"
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#121418] border-b border-white/10 px-6 py-5 flex flex-col gap-4 animate-in fade-in duration-200">
          {[
            { name: 'Platform', href: '/#platform' },
            { name: 'Capabilities', href: '/#capabilities' },
            { name: 'How It Works', href: '/#how-it-works' },
            { name: 'Security', href: '/#security' },
            { name: 'FAQ', href: '/#faq' }
          ].map((item) => (
            <button
              key={item.name}
              onClick={() => handleNavClick(item.href)}
              className="text-[#F5F3EE] text-left text-base py-2 border-b border-white/5 bg-transparent"
            >
              {item.name}
            </button>
          ))}

          <div className="flex flex-col gap-3 pt-2">
            <button
              onClick={() => handleNavClick('/auth')}
              className="btn-secondary w-full justify-center"
            >
              Sign In
            </button>
            <button
              onClick={() => handleNavClick('/app')}
              className="btn-bronze w-full justify-center"
            >
              <span>Launch App</span>
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      )}
    </header>
  );
};
