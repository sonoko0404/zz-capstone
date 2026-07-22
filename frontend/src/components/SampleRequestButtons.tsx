import { ArrowUpRight } from 'lucide-react'

interface SampleRequestButtonsProps {
  samples: string[]
  disabled: boolean
  onSelect: (sample: string) => void
}

export function SampleRequestButtons({
  samples,
  disabled,
  onSelect,
}: SampleRequestButtonsProps) {
  return (
    <div className="sample-requests" aria-label="Sample BI requests">
      {samples.slice(0, 5).map((sample) => (
        <button
          className="sample-request"
          disabled={disabled}
          key={sample}
          onClick={() => onSelect(sample)}
          type="button"
        >
          <span>{sample}</span>
          <ArrowUpRight aria-hidden="true" size={15} />
        </button>
      ))}
    </div>
  )
}
