import logo from '../assets/bookinguru-logo.png'

/**
 * BookinGuru's actual logo (icon + wordmark), supplied by Robin. The artwork
 * is dark-on-transparent, so it's mounted on a white plaque here — the app
 * shell is dark navy and the wordmark would be unreadable directly on it.
 */
export default function BrandMark({ size = 32, radius = 'rounded-lg' }) {
  return (
    <div
      className={`${radius} bg-white flex items-center justify-center shadow-lg shrink-0`}
      style={{ height: size, padding: size * 0.14 }}
    >
      <img
        src={logo}
        alt="BookinGuru"
        style={{ height: size * 0.72, width: 'auto' }}
        className="object-contain select-none"
      />
    </div>
  )
}
