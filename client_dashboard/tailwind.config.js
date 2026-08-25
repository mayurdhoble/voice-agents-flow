export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          dark:     '#0A1628',   // navy — logo dark blue
          darker:   '#060E1A',   // deeper navy
          blue:     '#2B7FFF',   // logo bright blue accent
          bluesoft: '#EBF3FF',   // light blue tint for hover/backgrounds
          mauve:    '#B5C4D8',   // muted blue-grey
          cream:    '#F5F8FF',   // cool off-white
          soft:     '#E8EFFE',   // light blue soft bg
          border:   '#D1DDF5',   // blue-tinted border
        },
      },
    },
  },
  plugins: [],
}
