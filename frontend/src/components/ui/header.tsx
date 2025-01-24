import deeptrust from "../../assets/logos/mainlogo.png";
import ExpiryTimer from "../Session/ExpiryTimer";

function Header() {
  return (
    <header
      id="header"
      className="w-full flex self-start items-center p-[--app-padding] justify-between"
    >
      <div className="group flex gap-8">
        <a 
          href="https://deeptrust.ai" 
          rel="noopener noreferrer"
          className="flex place-content-center transition-all"
        >
          <img src={deeptrust} alt="TerifAI Logo" className="w-auto h-12" />
        </a>
      </div>
      <ExpiryTimer />
    </header>
  );
}

export default Header;
