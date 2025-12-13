import React from "react";
import "./TripleToggleSwitch.css";

const defaultProps = {
    labels: {
        left: { title: "left", value: "left" },
        center: { title: "center", value: "center" },
        right: { title: "right", value: "right" }
    },
    onChange: (value) => console.log("value:", value)
};

class TripleToggleSwitch extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            switchPosition: "center", // INTENTIONALLY DEFAULT TO CENTER (or props-based if passed later)
            animation: null
        };
    }

    // Allow controlling from parent if needed, though this component as written by user holds its own state.
    // We'll add componentDidUpdate to sync if props change drastically, but let's stick to the user's class structure primarily.
    componentDidMount() {
        // If props provide an initial value, we could set it conformingly.
        // For now, we'll rely on the parent initializing logic or default to 'center' (value 2).
        if (this.props.value) {
            const pos = this.mapValueToPosition(this.props.value);
            this.setState({ switchPosition: pos });
        }
    }

    componentDidUpdate(prevProps) {
        if (prevProps.value !== this.props.value) {
            const pos = this.mapValueToPosition(this.props.value);
            if (pos !== this.state.switchPosition) {
                // We need to calculate animation if we strictly want animation on external updates too,
                // but usually state drives animation. For fast feedback let's just snap or re-run getSwitchAnimation logic?
                // Since the user's script `getSwitchAnimation` sets state AND calls onChange, we should be careful to avoid loops.
                // We'll just update position sans animation if controlled externally to avoid double-events, or trust the internal click.
                this.setState({ switchPosition: pos });
            }
        }
    }

     mapValueToPosition(val) {
        if (val === 1 || val === "left") return "left";
        if (val === 2 || val === "center") return "center";
        if (val === 3 || val === "right") return "right";
        return "center";
    }

    getSwitchAnimation = (value) => {
        const { switchPosition } = this.state;
        let animation = null;
        if (value === "center" && switchPosition === "left") {
            animation = "left-to-center";
        } else if (value === "right" && switchPosition === "center") {
            animation = "center-to-right";
        } else if (value === "center" && switchPosition === "right") {
            animation = "right-to-center";
        } else if (value === "left" && switchPosition === "center") {
            animation = "center-to-left";
        } else if (value === "right" && switchPosition === "left") {
            animation = "left-to-right";
        } else if (value === "left" && switchPosition === "right") {
            animation = "right-to-left";
        }

        this.props.onChange(value);
        this.setState({ switchPosition: value, animation });
    };

    render() {
        const { labels } = this.props;

        return (
            <div className="main-container">
                <div
                    className={`switch ${this.state.animation} ${this.state.switchPosition}-position`}
                ></div>

                <input
                    onChange={(e) => this.getSwitchAnimation(e.target.value)}
                    name="map-switch"
                    id="left"
                    type="radio"
                    value="left"
                    checked={this.state.switchPosition === "left"}
                />
                <label
                    className={`left-label ${this.state.switchPosition === "left" && "black-font"
                        }`}
                    htmlFor="left"
                >
                    <h4>{labels.left.title}</h4>
                </label>

                <input
                    onChange={(e) => this.getSwitchAnimation(e.target.value)}
                    name="map-switch"
                    id="center"
                    type="radio"
                    value="center"
                    checked={this.state.switchPosition === "center"}
                />
                <label
                    className={`center-label ${this.state.switchPosition === "center" && "black-font"
                        }`}
                    htmlFor="center"
                >
                    <h4>{labels.center.title}</h4>
                </label>

                <input
                    onChange={(e) => this.getSwitchAnimation(e.target.value)}
                    name="map-switch"
                    id="right"
                    type="radio"
                    value="right"
                    checked={this.state.switchPosition === "right"}
                />
                <label
                    className={`right-label ${this.state.switchPosition === "right" && "black-font"
                        }`}
                    htmlFor="right"
                >
                    <h4>{labels.right.title}</h4>
                </label>
            </div>
        );
    }
}

TripleToggleSwitch.defaultProps = defaultProps;

export default TripleToggleSwitch;
