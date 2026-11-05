import React from "react";

export const PageContainer: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = "" }) => (
  <div
    className={`mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-8 xl:max-w-[1440px] 2xl:max-w-[1600px] ${className}`}
  >
    {children}
  </div>
);

export const CardGrid: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = "" }) => (
  <div
    className={`grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 ${className}`}
  >
    {children}
  </div>
);